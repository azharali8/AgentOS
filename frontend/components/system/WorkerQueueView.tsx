import React, { useState, useEffect } from 'react';

interface WorkerInfo {
  worker_id: string;
  hostname: string;
  process_id: number;
  capabilities: string[];
  active_tasks: number;
  max_tasks: number;
  status: string;
  last_heartbeat: string | null;
}

interface QueueStats {
  backend: string;
  pending_count?: number;
  running_count?: number;
  dead_letter_count?: number;
  total_tasks?: number;
  queued?: number;
  running?: number;
  completed?: number;
  failed?: number;
}

export const WorkerQueueView: React.FC = () => {
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [queueStats, setQueueStats] = useState<QueueStats | null>(null);
  const [redisStatus, setRedisStatus] = useState<string>('CHECKING');
  const [loading, setLoading] = useState<boolean>(true);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [workersRes, queueRes, healthRes] = await Promise.all([
        fetch('/api/v1/system/workers').catch(() => null),
        fetch('/api/v1/system/queue').catch(() => null),
        fetch('/api/v1/system/health').catch(() => null),
      ]);

      if (workersRes && workersRes.ok) {
        const data = await workersRes.json();
        setWorkers(data.workers || []);
      }

      if (queueRes && queueRes.ok) {
        const qData = await queueRes.json();
        setQueueStats(qData);
      }

      if (healthRes && healthRes.ok) {
        const hData = await healthRes.json();
        setRedisStatus(hData.distributed?.redis_status || 'HEALTHY');
      }
    } catch (err) {
      console.error('Failed to load worker/queue status', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Distributed Worker Cluster</h1>
          <p className="text-sm text-gray-500">Real-time status of multi-node execution workers and task queues</p>
        </div>
        <div className="flex items-center space-x-3">
          <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
            redisStatus === 'HEALTHY' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
          }`}>
            Redis: {redisStatus}
          </span>
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md shadow-sm"
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Queue Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
          <div className="text-sm font-medium text-gray-500">Active Workers</div>
          <div className="mt-1 text-3xl font-semibold text-gray-900 dark:text-white">
            {workers.filter(w => w.status === 'READY' || w.status === 'BUSY').length} / {workers.length}
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
          <div className="text-sm font-medium text-gray-500">Queued Tasks</div>
          <div className="mt-1 text-3xl font-semibold text-blue-600">
            {queueStats?.pending_count ?? queueStats?.queued ?? 0}
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
          <div className="text-sm font-medium text-gray-500">Running Tasks</div>
          <div className="mt-1 text-3xl font-semibold text-yellow-600">
            {queueStats?.running_count ?? queueStats?.running ?? 0}
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
          <div className="text-sm font-medium text-gray-500">Dead Letter Queue</div>
          <div className="mt-1 text-3xl font-semibold text-red-600">
            {queueStats?.dead_letter_count ?? 0}
          </div>
        </div>
      </div>

      {/* Worker Fleet Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Registered Worker Nodes</h2>
        </div>
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Worker ID</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Capabilities</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Load</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last Heartbeat</th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            {workers.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-sm text-gray-500">
                  No active workers registered. Start worker processes using <code>python -m backend.scripts.run_worker</code>.
                </td>
              </tr>
            ) : (
              workers.map((w) => (
                <tr key={w.worker_id}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-mono font-medium text-gray-900 dark:text-white">
                    {w.worker_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                      w.status === 'READY' ? 'bg-green-100 text-green-800' :
                      w.status === 'BUSY' ? 'bg-blue-100 text-blue-800' :
                      w.status === 'DRAINING' ? 'bg-yellow-100 text-yellow-800' :
                      w.status === 'UNHEALTHY' ? 'bg-orange-100 text-orange-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {w.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    <div className="flex flex-wrap gap-1">
                      {w.capabilities.map((c) => (
                        <span key={c} className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded">
                          {c}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {w.active_tasks} / {w.max_tasks} tasks
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {w.last_heartbeat ? new Date(w.last_heartbeat).toLocaleTimeString() : 'N/A'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default WorkerQueueView;
