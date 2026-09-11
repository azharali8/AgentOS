"use client";

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Square, X, Volume2, VolumeX, Loader2 } from 'lucide-react';
import { AgentOSClient } from '../../lib/api';
import { VoiceEndpoint } from '../../lib/voice-endpoint';

interface VoiceControlProps {
  client: AgentOSClient;
  onTaskCreated?: (taskId: string) => void;
  className?: string;
  compact?: boolean;
}

export const VoiceControl: React.FC<VoiceControlProps> = ({client, onTaskCreated, className = ''}) => {
  const [state, setState] = useState<'idle' | 'listening' | 'processing' | 'error'>('idle');
  const [transcript, setTranscript] = useState('');
  const [feedback, setFeedback] = useState('');
  const [muted, setMuted] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const active = useRef(false);
  const session = useRef('');
  const recorder = useRef<MediaRecorder | null>(null);
  const context = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const generation = useRef(0);
  const busy = useRef(false);
  const mounted = useRef(true);
  const startRef = useRef<() => void>(() => {});
  const mutedRef = useRef(muted);
  mutedRef.current = muted;

  const release = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    if (context.current) void context.current.close().catch(() => {});
    context.current = null;
  }, []);

  const cancel = useCallback(() => {
    active.current = false;
    generation.current++;
    if (recorder.current?.state === 'recording') {
      recorder.current.onstop = null;
      recorder.current.stop();
    }
    release(); busy.current = false;
    window.speechSynthesis?.cancel();
    if (mounted.current) { setState('idle'); setSpeaking(false); }
  }, [release]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; cancel(); };
  }, [cancel]);

  const speak = useCallback((text: string, after?: () => void) => {
    if (mutedRef.current || !window.speechSynthesis) { after?.(); return; }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.slice(0, 1800));
    setSpeaking(true);
    utterance.onend = () => { if (mounted.current) setSpeaking(false); after?.(); };
    utterance.onerror = () => { if (mounted.current) { setSpeaking(false); setFeedback('Speech playback failed. You can read the response and use Voice to continue.'); } };
    // Do not restart listening if playback failed; allow the user to retry.
    window.speechSynthesis.speak(utterance);
  }, []);

  useEffect(() => {
    if (!taskId) return;
    let disposed = false;
    let polling = false;
    let announced = '';
    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const task = await client.getTask(taskId);
        if (disposed) return;
        if (['COMPLETED', 'FAILED', 'CANCELLED', 'WAITING_APPROVAL'].includes(task.status) && task.status !== announced) {
          // Do not interrupt a user's utterance or an in-flight conversational turn.
          if (busy.current || window.speechSynthesis?.speaking) return;
          announced = task.status;
          const text = task.status === 'WAITING_APPROVAL'
            ? 'This task needs approval. Review the proposed changes in Approvals.'
            : task.result_summary || task.error || `Task ${task.status.toLowerCase()}.`;
          setFeedback(text);
          if (task.status !== 'WAITING_APPROVAL') setTaskId(null);
          if (active.current) { setOpen(true); speak(text); }
        }
      } catch { /* The execution view also reports stream connectivity. Retry polling. */ }
      finally { polling = false; }
    };
    const interval = setInterval(poll, 2000);
    void poll();
    return () => { disposed = true; clearInterval(interval); };
  }, [taskId, client, speak]);

  const start = async () => {
    if (busy.current) return;
    busy.current = true;
    active.current = true;
    const turn = ++generation.current;
    setOpen(true); setFeedback('');
    window.speechSynthesis?.cancel();
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder || !window.AudioContext) {
        throw new Error('This browser cannot capture microphone audio. Use a supported browser over HTTPS or localhost.');
      }
      const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}});
      if (!mounted.current || turn !== generation.current) { stream.getTracks().forEach(t => t.stop()); return; }
      streamRef.current = stream;
      const audio = new AudioContext();
      context.current = audio;
      await audio.resume();
      if (!mounted.current || turn !== generation.current) { release(); return; }
      const analyser = audio.createAnalyser();
      analyser.fftSize = 2048;
      audio.createMediaStreamSource(stream).connect(analyser);
      const data = new Float32Array(analyser.fftSize);
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t));
      const capture = new MediaRecorder(stream, mime ? {mimeType: mime} : undefined);
      recorder.current = capture;
      const chunks: Blob[] = [];
      const endpoint = new VoiceEndpoint(performance.now());
      capture.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      capture.onstop = async () => {
        release();
        if (!mounted.current || turn !== generation.current) return;
        if (!endpoint.heardSpeech) { busy.current = false; setState('error'); setFeedback('No speech detected. Please try again.'); return; }
        setState('processing');
        try {
          if (!session.current) session.current = crypto.randomUUID();
          // The single combined endpoint waits for a completed provider transcript.
          const result = await client.executeVoiceCommand(new Blob(chunks, {type: capture.mimeType || 'audio/webm'}), true, false, session.current);
          if (!mounted.current || turn !== generation.current) return;
          setTranscript(result.transcript); setFeedback(result.tts_summary);
          setState('idle'); busy.current = false;
          const continueConversation = !['failed', 'error', 'denied'].includes(result.status);
          speak(result.tts_summary, continueConversation ? () => {
            if (mounted.current && turn === generation.current) startRef.current();
          } : undefined);
          if (result.task_id) {
            setTaskId(result.task_id);
            onTaskCreated?.(result.task_id);
          }
        } catch (err) {
          if (mounted.current && turn === generation.current) {
            busy.current = false; setState('error');
            setFeedback(err instanceof Error ? err.message : 'Voice execution failed.');
          }
        }
      };
      capture.onerror = () => { cancel(); setState('error'); setFeedback('Microphone recording failed. Please retry.'); };
      capture.start(250);
      setState('listening');
      timer.current = setInterval(() => {
        const now = performance.now();
        analyser.getFloatTimeDomainData(data);
        const rms = Math.sqrt(data.reduce((sum, value) => sum + value * value, 0) / data.length);
        const action = endpoint.sample(rms, now);
        if (action === 'finish' && capture.state === 'recording') capture.stop();
        else if (action === 'discard') {
          // A time limit is not an utterance boundary: discard truncated speech.
          cancel(); active.current = true;
          setState(endpoint.heardSpeech ? 'error' : 'idle');
          setFeedback(endpoint.heardSpeech ? 'Recording timed out. Please speak a shorter instruction.' : 'Microphone paused after silence. Use Voice when you are ready to continue.');
        }
      }, 50);
    } catch (err) {
      release(); busy.current = false;
      if (mounted.current && turn === generation.current) {
        setState('error'); setFeedback(err instanceof Error ? err.message : 'Microphone access failed.');
      }
    }
  };
  startRef.current = () => { void start(); };

  return <div className={`relative ${className}`}>
    <button type="button" onClick={() => { if (state === 'listening') recorder.current?.stop(); else if (!busy.current) void start(); }}
      disabled={state === 'processing'} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-indigo-50 text-indigo-700 text-xs font-semibold">
      {state === 'processing' ? <Loader2 className="w-4 h-4 animate-spin" /> : state === 'listening' ? <Square className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
      {state === 'listening' ? 'Finish turn' : state === 'processing' ? 'Processing voice' : 'Voice'}
    </button>
    {open && <div className="absolute right-0 top-12 w-80 max-w-[90vw] bg-white border border-slate-200 rounded-2xl shadow-lg p-4 space-y-3 z-50" role="status" aria-live="polite">
      <div className="flex justify-between items-center text-xs font-semibold">
        <span>{speaking ? 'Speaking' : state === 'listening' ? 'Listening — pause when finished' : state === 'processing' ? 'Recognizing and processing your request' : 'Voice Supervisor'}</span>
        <button aria-label={muted ? 'Unmute speech' : 'Mute speech'} onClick={() => { setMuted(!muted); if (!muted) window.speechSynthesis?.cancel(); }}>
          {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>
      </div>
      {transcript && <div><p className="text-[10px] text-slate-500">What AgentOS heard</p><p className="text-xs">{transcript}</p></div>}
      {feedback && <p className={`text-xs whitespace-pre-wrap max-h-48 overflow-auto ${state === 'error' ? 'text-rose-700' : 'text-slate-700'}`}>{feedback}</p>}
      <button className="text-xs text-slate-500 flex gap-1" onClick={() => { cancel(); setOpen(false); }}><X className="w-3 h-3" />{state === 'listening' ? 'End voice session' : 'Close voice'}</button>
    </div>}
  </div>;
};
