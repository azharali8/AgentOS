'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Mic,
  MicOff,
  Square,
  Sparkles,
  Loader2,
  AlertCircle,
  Volume2,
  VolumeX,
  Send,
  X,
  Radio,
  CheckCircle2,
} from 'lucide-react';
import { AgentOSClient } from '../../lib/api';
import { VoiceExecuteResponse } from '../../types';

interface VoiceControlProps {
  client: AgentOSClient;
  onTaskCreated?: (taskId: string) => void;
  onTranscriptReady?: (transcript: string) => void;
  className?: string;
  compact?: boolean;
}

type VoiceState = 'idle' | 'recording' | 'transcribing' | 'review' | 'executing' | 'error';

export const VoiceControl: React.FC<VoiceControlProps> = ({
  client,
  onTaskCreated,
  onTranscriptReady,
  className = '',
  compact = false,
}) => {
  const [state, setState] = useState<VoiceState>('idle');
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [transcript, setTranscript] = useState('');
  const [ttsFeedback, setTtsFeedback] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [ttsMuted, setTtsMuted] = useState(false);
  const [isAssemblyAI, setIsAssemblyAI] = useState(true);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Check voice provider status on mount
  useEffect(() => {
    client.getVoiceStatus().then((status) => {
      setIsAssemblyAI(status?.stt_provider?.toLowerCase().includes('assemblyai') ?? true);
    }).catch(() => {});
  }, [client]);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const speakText = useCallback((text: string) => {
    if (ttsMuted || typeof window === 'undefined' || !window.speechSynthesis) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn('Browser SpeechSynthesis error:', e);
    }
  }, [ttsMuted]);

  const startRecording = async () => {
    setErrorMsg(null);
    setTranscript('');
    setTtsFeedback(null);
    setRecordingSeconds(0);
    audioChunksRef.current = [];

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setErrorMsg('Microphone recording is not supported by your browser.');
      setState('error');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
      }

      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        // Stop all audio tracks to release microphone hardware
        stream.getTracks().forEach((track) => track.stop());

        const capturedBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });
        setAudioBlob(capturedBlob);

        if (capturedBlob.size < 100) {
          setErrorMsg('No audible sound detected. Please try speaking again.');
          setState('error');
          return;
        }

        // Send to backend for transcription
        await handleTranscribe(capturedBlob);
      };

      recorder.start(250); // chunk every 250ms
      setState('recording');

      // Start recording timer
      timerRef.current = setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 60) {
            // Auto stop at 60s
            stopRecording();
            return 60;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (err: any) {
      console.error('Microphone access denied or failed:', err);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setErrorMsg('Microphone access denied. Please grant microphone permission in your browser.');
      } else {
        setErrorMsg(err.message || 'Failed to start microphone recording.');
      }
      setState('error');
    }
  };

  const stopRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  const cancelRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current) {
      try {
        if (mediaRecorderRef.current.state === 'recording') {
          mediaRecorderRef.current.stop();
        }
        mediaRecorderRef.current.stream?.getTracks().forEach((t) => t.stop());
      } catch {}
    }
    audioChunksRef.current = [];
    setAudioBlob(null);
    setState('idle');
    setRecordingSeconds(0);
    setErrorMsg(null);
  };

  const handleTranscribe = async (blob: Blob) => {
    setState('transcribing');
    setErrorMsg(null);
    try {
      const res = await client.transcribeAudio(blob);
      const recognized = res.transcript?.trim() || '';
      if (!recognized) {
        setErrorMsg('No speech recognized. Please try speaking closer to your microphone.');
        setState('error');
        return;
      }

      setTranscript(recognized);
      if (onTranscriptReady) {
        onTranscriptReady(recognized);
      }
      setState('review');
    } catch (err: any) {
      console.error('Transcription failed:', err);
      setErrorMsg(err.message || 'Speech-to-Text processing failed.');
      setState('error');
    }
  };

  const handleExecute = async () => {
    if (!audioBlob && !transcript.trim()) return;
    setState('executing');
    setErrorMsg(null);

    try {
      let res: VoiceExecuteResponse;
      if (audioBlob) {
        res = await client.executeVoiceCommand(audioBlob, true, false);
      } else {
        // Fallback to text task creation if user edited the transcript
        const task = await client.createTask(transcript.trim(), 1);
        res = {
          status: 'planning',
          transcript: transcript.trim(),
          task_id: task.task_id,
          project_created: false,
          tts_summary: `Starting task: ${transcript.trim().slice(0, 80)}`,
          provider: 'text',
        };
      }

      setTtsFeedback(res.tts_summary);
      speakText(res.tts_summary);

      if (res.task_id && onTaskCreated) {
        onTaskCreated(res.task_id);
      }

      // Briefly show success before returning to idle
      setTimeout(() => {
        setState('idle');
        setTranscript('');
        setAudioBlob(null);
      }, 1500);
    } catch (err: any) {
      console.error('Voice execution failed:', err);
      setErrorMsg(err.message || 'Failed to submit voice task to AgentOS.');
      setState('error');
    }
  };

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Compact Header / Nav Bar Variant
  if (compact) {
    return (
      <div className={`relative inline-flex items-center ${className}`}>
        {state === 'idle' && (
          <button
            type="button"
            onClick={startRecording}
            title="Voice Command (AssemblyAI)"
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 rounded-xl text-xs font-semibold shadow-2xs transition-all"
          >
            <Mic className="w-3.5 h-3.5 text-indigo-600" />
            <span className="hidden sm:inline">Voice</span>
          </button>
        )}

        {state === 'recording' && (
          <button
            type="button"
            onClick={stopRecording}
            title="Click to Finish Recording"
            className="flex items-center space-x-2 px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-semibold shadow-xs transition-all animate-pulse"
          >
            <Square className="w-3 h-3 fill-white" />
            <span>{formatSeconds(recordingSeconds)}</span>
          </button>
        )}

        {state === 'transcribing' && (
          <div className="flex items-center space-x-1.5 px-3 py-1.5 bg-amber-50 text-amber-800 border border-amber-200 rounded-xl text-xs font-medium">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span className="hidden sm:inline">Transcribing...</span>
          </div>
        )}
      </div>
    );
  }

  // Full Rich Card Variant (Dashboard Integration)
  return (
    <div className={`transition-all duration-200 ${className}`}>
      {/* 1. Idle state — Mic Button */}
      {state === 'idle' && (
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={startRecording}
            className="flex items-center space-x-2 px-3.5 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 rounded-xl text-xs font-semibold shadow-2xs transition-all group"
          >
            <div className="w-2 h-2 rounded-full bg-indigo-600 group-hover:animate-ping" />
            <Mic className="w-3.5 h-3.5 text-indigo-600" />
            <span>Speak Command</span>
          </button>
          <span className="text-[11px] text-slate-400">
            Powered by AssemblyAI
          </span>
        </div>
      )}

      {/* 2. Recording state */}
      {state === 'recording' && (
        <div className="flex items-center justify-between p-3.5 bg-rose-50/80 border border-rose-200 rounded-2xl animate-in fade-in duration-150">
          <div className="flex items-center space-x-3">
            <div className="relative flex items-center justify-center">
              <span className="absolute w-6 h-6 rounded-full bg-rose-500/30 animate-ping" />
              <span className="w-3 h-3 rounded-full bg-rose-600" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xs font-bold text-rose-900">AgentOS is listening...</span>
                <span className="font-mono text-xs font-semibold text-rose-700 bg-rose-100/80 px-2 py-0.5 rounded-md">
                  {formatSeconds(recordingSeconds)}
                </span>
              </div>
              <p className="text-[11px] text-rose-600/80 mt-0.5">
                Speak your engineering instruction clearly into your microphone
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={cancelRecording}
              className="p-1.5 text-rose-400 hover:text-rose-700 hover:bg-rose-100/80 rounded-xl transition-colors"
              title="Cancel recording"
            >
              <X className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={stopRecording}
              className="flex items-center space-x-1.5 px-3.5 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold shadow-xs transition-all"
            >
              <Square className="w-3 h-3 fill-white" />
              <span>Finish &amp; Transcribe</span>
            </button>
          </div>
        </div>
      )}

      {/* 3. Transcribing state */}
      {state === 'transcribing' && (
        <div className="flex items-center justify-between p-3.5 bg-indigo-50/60 border border-indigo-100 rounded-2xl animate-in fade-in">
          <div className="flex items-center space-x-3">
            <Loader2 className="w-5 h-5 text-indigo-600 animate-spin" />
            <div>
              <span className="text-xs font-bold text-indigo-900">
                Transcribing with AssemblyAI...
              </span>
              <p className="text-[11px] text-indigo-600/80">
                Converting your voice into a structured engineering command
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={cancelRecording}
            className="p-1.5 text-slate-400 hover:text-slate-600 rounded-xl"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 4. Review & Confirm state */}
      {state === 'review' && (
        <div className="p-4 bg-white border border-indigo-100 rounded-2xl shadow-sm space-y-3 animate-in fade-in zoom-in-95">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              <span className="text-xs font-bold text-slate-900">Voice Command Recognized</span>
              <span className="text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-md font-medium">
                AssemblyAI
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => setTtsMuted(!ttsMuted)}
                title={ttsMuted ? 'Unmute voice feedback' : 'Mute voice feedback'}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg"
              >
                {ttsMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4 text-indigo-600" />}
              </button>
              <button
                type="button"
                onClick={cancelRecording}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg"
                title="Discard transcript"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="relative">
            <textarea
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              rows={2}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-900 font-sans focus:outline-none focus:ring-1 focus:ring-indigo-500/30 resize-none leading-relaxed"
              placeholder="Edit recognized command if needed..."
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <button
              type="button"
              onClick={startRecording}
              className="text-xs text-slate-500 hover:text-indigo-600 font-medium"
            >
              Re-record voice
            </button>
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={cancelRecording}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-xl font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExecute}
                disabled={!transcript.trim()}
                className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold shadow-xs transition-all"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Execute with Supervisor</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. Executing state */}
      {state === 'executing' && (
        <div className="flex items-center space-x-3 p-3.5 bg-emerald-50 border border-emerald-200 rounded-2xl animate-in fade-in">
          <Loader2 className="w-5 h-5 text-emerald-600 animate-spin shrink-0" />
          <div className="flex-1">
            <span className="text-xs font-bold text-emerald-900">
              Delegating to AgentOS Supervisor...
            </span>
            <p className="text-[11px] text-emerald-700 mt-0.5 truncate">
              {ttsFeedback || `Starting: ${transcript.slice(0, 60)}...`}
            </p>
          </div>
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
        </div>
      )}

      {/* 6. Error state */}
      {state === 'error' && (
        <div className="flex items-start justify-between p-3.5 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-700 animate-in fade-in">
          <div className="flex items-start space-x-2.5">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-rose-900">Voice Recognition Error</span>
              <p className="text-[11px] text-rose-700 mt-0.5">{errorMsg || 'An unknown error occurred.'}</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={startRecording}
              className="px-2.5 py-1 bg-rose-600 text-white rounded-lg text-xs font-semibold hover:bg-rose-700 transition-colors"
            >
              Retry
            </button>
            <button
              type="button"
              onClick={cancelRecording}
              className="p-1 text-rose-500 hover:text-rose-700"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
