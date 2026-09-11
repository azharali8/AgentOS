import { useState, useEffect } from 'react';
import { TaskEvent } from '../types';

export function useTaskEventStream(taskId: string | null, token?: string | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setEvents([]); setIsConnected(false); setError(null);
    if (!taskId) return;
    let disposed = false;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let heartbeat: ReturnType<typeof setInterval>;
    let lastEventId = '';
    const seen = new Set<string>();
    const connect = () => {
      const url = new URL(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      if (process.env.NEXT_PUBLIC_WS_HOST) url.host = process.env.NEXT_PUBLIC_WS_HOST;
      url.pathname = `/api/v1/events/stream/${encodeURIComponent(taskId)}`;
      if (token) url.searchParams.set('token', token);
      if (lastEventId) url.searchParams.set('last_event_id', lastEventId);
      socket = new WebSocket(url.toString());
      socket.onopen = () => {
        if (disposed) return;
        setIsConnected(true); setError(null);
        heartbeat = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send('ping');
        }, 20000);
      };
      socket.onmessage = ({data}) => {
        if (disposed || data === 'pong') return;
        try {
          const event = JSON.parse(data) as TaskEvent;
          if (!event.event_id || event.task_id !== taskId || seen.has(event.event_id)) return;
          seen.add(event.event_id); lastEventId = event.event_id;
          setEvents(prev => [...prev, event]);
        } catch { setError('Invalid event received'); }
      };
      socket.onerror = () => { if (!disposed) setError('Event stream interrupted; reconnecting'); };
      socket.onclose = () => {
        clearInterval(heartbeat);
        if (!disposed) { setIsConnected(false); retry = setTimeout(connect, 15000); }
      };
    };
    connect();
    return () => {
      disposed = true; clearTimeout(retry); clearInterval(heartbeat); socket?.close();
    };
  }, [taskId, token]);
  return { events, isConnected, error };
}
