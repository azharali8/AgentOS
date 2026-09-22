"use client";

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Square, X, Volume2, VolumeX, Loader2, AudioLines } from 'lucide-react';
import { AgentOSClient } from '../../lib/api';
import { VoicePlayback, reconnectDelay, supervisorStage } from '../../lib/voice-stream';
import { BrowserSpeech } from '../../lib/browser-speech';

interface VoiceControlProps {
  client: AgentOSClient;
  onTaskCreated?: (taskId: string) => void;
  className?: string;
  compact?: boolean;
  readAloud?: boolean;
  onActiveChange?: (active:boolean)=>void;
  disabled?:boolean;
}

export const VoiceControl: React.FC<VoiceControlProps> = ({client, onTaskCreated, className = '',readAloud=true,onActiveChange,disabled=false}) => {
  const mode=useRef<'once'|'live'>('live');
  const results=useRef(new Set<number>());
  const [state, setState] = useState('idle');
  const [transcript, setTranscript] = useState('');
  const [final, setFinal] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [progressError, setProgressError] = useState('');
  const [muted, setMuted] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [stage, setStage] = useState('');
  const [open, setOpen] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const active = useRef(false);
  const session = useRef('');
  const socket = useRef<WebSocket | null>(null);
  const context = useRef<AudioContext | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const worklet = useRef<AudioWorkletNode | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const speech = useRef<BrowserSpeech | null>(null);
  const mutedRef = useRef(muted);
  mutedRef.current = muted || !readAloud;
  useEffect(()=>{onActiveChange?.(['connecting','reconnecting','listening','processing'].includes(state));},[state,onActiveChange]);

  const stopSpeech = useCallback(() => {
    speech.current?.stop();
    setSpeaking(false);
  }, []);
  const playback = useRef<VoicePlayback | null>(null);
  if (!playback.current) playback.current = new VoicePlayback(stopSpeech);

  const release = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    worklet.current?.disconnect(); worklet.current = null;
    stream.current?.getTracks().forEach(t => t.stop()); stream.current = null;
    if (context.current) void context.current.close().catch(() => {});
    context.current = null;
  }, []);

  const stop = useCallback(() => {
    active.current = false; generation.current++;
    const ws = socket.current; socket.current = null;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send('{"type":"Stop"}');
      // Give the server time to receive AssemblyAI's Termination acknowledgement.
      setTimeout(() => ws.close(), 3500);
    } else ws?.close();
    release(); stopSpeech(); setState('idle');
  }, [release, stopSpeech]);

  useEffect(() => () => { stop(); }, [stop]);

  const speak = useCallback((text: string) => {
    if (!active.current || mode.current==='once' || mutedRef.current || playback.current?.userSpeaking) return;
    if (!window.speechSynthesis) { setError('Browser speech is unavailable. Read the response below.'); return; }
    if (!speech.current) speech.current = new BrowserSpeech(window.speechSynthesis,
      text => new SpeechSynthesisUtterance(text), setSpeaking, setError,
      text => {
        if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({type: 'Playback', text}));
      });
    speech.current.speak(text);
  }, []);

  useEffect(() => {
    if (!taskId) return;
    let disposed = false, polling = false, announced = '';
    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const [task, events] = await Promise.all([client.getTask(taskId), client.getTaskEvents(taskId)]);
        if (disposed) return;
        setProgressError('');
        setStage(supervisorStage(task.status, events));
        if (['COMPLETED', 'FAILED', 'CANCELLED', 'WAITING_APPROVAL'].includes(task.status) && announced !== task.status && !playback.current?.userSpeaking) {
          announced = task.status;
          const text = task.status === 'WAITING_APPROVAL' ? 'Awaiting approval. Review the proposed changes in Approvals.' : task.result_summary || task.error || `Task ${task.status.toLowerCase()}.`;
          setFeedback(text); speak(text);
        }
      } catch {
        if (!disposed) setProgressError('Supervisor progress is unavailable. Check the backend connection; task success is not confirmed.');
      } finally { polling = false; }
    };
    const interval = setInterval(poll, 4000); void poll();
    return () => { disposed = true; clearInterval(interval); };
  }, [taskId, client, speak]);

  useEffect(()=>{if(!readAloud)stopSpeech();},[readAloud,stopSpeech]);

  const start = async (selectedMode:'once'|'live') => {
    if(disabled)return;
    mode.current=selectedMode;results.current.clear();setTaskId(null);setStage('');setProgressError('');
    if (active.current) return;
    active.current = true;
    const gen = ++generation.current;
    setOpen(true); setState('connecting'); setError(''); setTranscript(''); setFeedback('');
    playback.current = new VoicePlayback(stopSpeech);
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext || !window.AudioWorkletNode) throw new Error('Live voice requires a browser with AudioWorklet and microphone support on HTTPS or localhost.');
      const media = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
      if (gen !== generation.current) { media.getTracks().forEach(t => t.stop()); return; }
      stream.current = media;
      const audio = new AudioContext(); context.current = audio;
      await audio.resume(); await audio.audioWorklet.addModule('/voice-capture.js');
      if (gen !== generation.current) return;
      const capture = new AudioWorkletNode(audio, 'agentos-voice-capture'); worklet.current = capture;
      audio.createMediaStreamSource(media).connect(capture); capture.connect(audio.destination);
      if (!session.current) session.current = crypto.randomUUID();
      let ready = false, attempts = 0;
      const connect = () => {
        if (!active.current || gen !== generation.current) return;
        ready = false; captured = false; let retryable = true, providerError = false;
        setState(attempts ? 'reconnecting' : 'connecting');
        const ws = client.openVoiceStream(session.current,mode.current); socket.current = ws;
        timer.current = setTimeout(() => { setError('Backend or speech provider did not start in time.'); ws.close(); }, 20000);
        ws.onmessage = event => {
          if (gen !== generation.current || ws !== socket.current) return;
          try {
            const message = JSON.parse(event.data);
            switch (message.type) {
              case 'Begin':
                if (timer.current) clearTimeout(timer.current);
                results.current.clear(); playback.current?.begin(); setTranscript(''); setFinal(false);
                ready = true; setState('connecting'); setError(''); break;
              case 'SpeechStarted':
                playback.current?.speechStarted(); setState('listening'); setTranscript(''); setFinal(false); break;
              case 'Turn':
                if (typeof message.transcript !== 'string' || typeof message.end_of_turn !== 'boolean') throw new Error('Invalid transcript');
                if (!message.end_of_turn && message.transcript.trim() && !playback.current?.userSpeaking) playback.current?.speechStarted();
                setTranscript(message.transcript); setFinal(message.end_of_turn);
                if (message.end_of_turn) {playback.current?.final(message.turn_order);if(mode.current==='once'&&message.transcript.trim()){retryable=false;release();}}
                break;
              case 'Processing':
                playback.current?.processing(message.turn_order); setState('processing'); break;
              case 'Result':
                if(results.current.has(message.turn_order))break;results.current.add(message.turn_order);
                setState('listening'); setFeedback(message.tts_summary);
                if (['failed', 'error', 'denied'].includes(message.status)) setError(message.tts_summary);
                if (message.task_id) { setTaskId(message.task_id); onTaskCreated?.(message.task_id); }
                if (playback.current?.canSpeak(message.turn_order)) speak(message.tts_summary);
                if(mode.current==='once'){stop();setState(['failed','error','denied'].includes(message.status)?'error':'completed');}
                break;
              case 'Notice': setFeedback(message.message); break;
              case 'Error':
                retryable = message.retryable === true; providerError = true; ready = false;
                setError(message.message); stopSpeech(); ws.close(); break;
              case 'Termination': ready = false; retryable = false; ws.close(); break;
            }
          } catch {
            retryable = false; providerError = true; setError('Malformed voice response. Session stopped without submitting client text.'); ws.close();
          }
        };
        ws.onerror = () => { setError('Voice connection failed. Check that the backend is running.'); };
        ws.onclose = () => {
          if (gen !== generation.current || ws !== socket.current) return;
          ready = false; stopSpeech();
          if (timer.current) clearTimeout(timer.current);
          const delay = reconnectDelay(attempts, retryable);
          if (delay !== null && active.current) {
            attempts++; setState('reconnecting');
            if (!providerError) setError('Voice disconnected. Reconnecting without replaying audio or commands. Check task progress before repeating a request.');
            timer.current = setTimeout(connect, delay);
          } else {
            active.current = false; release(); setState('error');
            if (!providerError) setError('Voice session ended. Check task progress before starting another session.');
          }
        };
      };
      let captured = false;
      capture.port.onmessage = event => {
        const ws = socket.current;
        if (!ready || !active.current || gen !== generation.current || ws?.readyState !== WebSocket.OPEN) return;
        if (ws.bufferedAmount > 64000) { ready = false; setError('Audio connection is too slow. Buffered speech was discarded.'); ws.close(); return; }
        if (!captured) { captured = true; setState('listening'); }
        ws.send(event.data);
      };
      media.getAudioTracks()[0].onended = () => { if (active.current) { stop(); setState('error'); setError('Microphone disconnected. Select a microphone and restart voice.'); } };
      connect();
    } catch (err) {
      if (gen !== generation.current) return;
      stop(); setState('error');
      setError(err instanceof DOMException && err.name === 'NotAllowedError' ? 'Microphone permission denied. Allow microphone access, then restart voice.' : err instanceof Error ? err.message : 'Unable to start live voice.');
    }
  };

  const label = state==='error' ? 'Voice request failed' : state==='completed' ? 'Command submitted' : speaking ? (active.current ? 'Speaking — listening for interruptions' : 'Speaking') : state === 'processing' ? 'Understanding request' : state === 'listening' ? 'Listening' : state === 'reconnecting' ? 'Reconnecting' : state === 'connecting' ? 'Connecting microphone' : 'Voice Supervisor';
  return <div className={`composer-voice ${className}`}>
    <button type="button" className="composer-icon" aria-label={active.current&&mode.current==='once'?'Stop microphone':'One-shot voice command'} title="Speak one command" disabled={disabled&&!active.current || active.current&&mode.current!=='once'} onClick={()=>{if(active.current)stop();else void start('once');}}>{active.current&&mode.current==='once'?<Square size={18}/>:<Mic size={19}/>}</button>
    <button type="button" className="composer-live" aria-label={active.current&&mode.current==='live'?'End Live Voice':'Start Live Voice'} title="Live Voice — continuous conversation" aria-pressed={active.current&&mode.current==='live'} disabled={disabled&&!active.current || active.current&&mode.current!=='live'} onClick={()=>{if(active.current)stop();else void start('live');}}>{active.current&&mode.current==='live'?<Square size={18}/>:<AudioLines size={20}/>}</button>
    {open && <div className="composer-voice-status">
      <div className="flex justify-between items-center gap-2 text-xs font-semibold" role="status" aria-live="polite">
        <span>{label}</span>
        {mode.current==='live' && readAloud && <button aria-label={muted ? 'Unmute speech' : 'Mute speech'} onClick={() => { setMuted(!muted); if (!muted) stopSpeech(); }}>
          {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>}
      </div>
      {transcript && <div><p className="text-[10px] text-slate-500">{final ? 'Confirmed turn' : 'Live transcript · not submitted'}</p><p className="text-sm break-words">{transcript}</p></div>}
      {stage && <p className="text-xs font-semibold text-indigo-700" role="status">Supervisor · {stage}</p>}
      {feedback && <p className="text-xs whitespace-pre-wrap break-words text-slate-700">{feedback}</p>}
      {progressError && <p className="text-xs text-amber-700" role="alert">{progressError}</p>}
      {error && <p className="text-xs text-rose-700" role="alert">{error}</p>}
      <p className="text-[10px] text-slate-400">Audio streams to AssemblyAI. Completed turns submit automatically. Headphones help prevent speaker echo.</p>
      <button className="text-xs text-slate-500 flex gap-1" onClick={() => { stop(); setOpen(false); }}><X className="w-3 h-3" />{active.current&&mode.current==='live'?'End Live Voice':'Close voice'}</button>
    </div>}
  </div>;
};
