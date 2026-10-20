"use client";

import { useState, useEffect } from "react";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Job {
  id: string;
  workflow_id: string;
  status: string;
  attempt: number;
  created_at: string;
  error_code?: string;
  error_message?: string;
}

interface Workflow {
  id: string;
  version: string;
  name: string;
  risk_level: string;
}

interface Health {
  status: string;
  version: string;
  workers_registered: string[];
}

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState("");
  const [jobPayload, setJobPayload] = useState("{}");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetchHealth();
    fetchWorkflows();
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchHealth = async () => {
    try {
      const res = await axios.get(`${API_BASE}/health`);
      setHealth(res.data);
    } catch (e) {
      console.error("Health check failed", e);
    }
  };

  const fetchWorkflows = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/v1/workflows`);
      setWorkflows(res.data.workflows);
    } catch (e) {
      console.error("Failed to fetch workflows", e);
    }
  };

  const fetchJobs = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/v1/jobs?limit=20`);
      setJobs(res.data.jobs);
    } catch (e) {
      console.error("Failed to fetch jobs", e);
    }
  };

  const runWorkflow = async () => {
    if (!selectedWorkflow) return;
    setLoading(true);
    setMessage("");
    try {
      let payload = {};
      try {
        payload = JSON.parse(jobPayload);
      } catch {
        setMessage("Invalid JSON payload");
        setLoading(false);
        return;
      }
      const res = await axios.post(`${API_BASE}/api/v1/workflows/${selectedWorkflow}/run`, {
        workflow_id: selectedWorkflow,
        payload,
      });
      setMessage(`Job created: ${res.data.job_id} - ${res.data.success ? "Success" : "Failed"}`);
      fetchJobs();
    } catch (e: any) {
      setMessage(`Error: ${e.response?.data?.detail || e.message}`);
    }
    setLoading(false);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "succeeded": return "text-green-600";
      case "failed": return "text-red-600";
      case "running": return "text-blue-600";
      case "queued": return "text-yellow-600";
      case "waiting": return "text-orange-600";
      case "retrying": return "text-purple-600";
      default: return "text-gray-600";
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Automation Empire OS</h1>
          <p className="text-gray-600 mt-1">Local-first automation operating system</p>
        </div>

        {/* Health & Workers */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold mb-2">System Health</h2>
            <div className={health?.status === "healthy" ? "text-green-600 font-mono" : "text-red-600 font-mono"}>
              {health?.status || "checking..."}
            </div>
            <div className="text-sm text-gray-500 mt-1">v{health?.version}</div>
            <div className="mt-4">
              <h3 className="text-sm font-medium">Registered Workers</h3>
              <div className="flex flex-wrap gap-2 mt-2">
                {health?.workers_registered.map((w: string) => (
                  <span key={w} className="px-2 py-1 bg-gray-100 rounded text-sm">{w}</span>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow md:col-span-2">
            <h2 className="text-lg font-semibold mb-4">Run Workflow</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Workflow</label>
                <select
                  value={selectedWorkflow}
                  onChange={(e) => setSelectedWorkflow(e.target.value)}
                  className="w-full p-2 border rounded"
                >
                  <option value="">Select workflow...</option>
                  {workflows.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} ({w.id}) - v{w.version}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Payload (JSON)</label>
                <textarea
                  value={jobPayload}
                  onChange={(e) => setJobPayload(e.target.value)}
                  rows={6}
                  className="w-full p-2 border rounded font-mono text-sm"
                  placeholder='{"campaign_source": "manual", "source_url": "https://..."}'
                />
              </div>
              <button
                onClick={runWorkflow}
                disabled={loading || !selectedWorkflow}
                className="px-6 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
              >
                {loading ? "Running..." : "Run Workflow"}
              </button>
              {message && (
                <div className={`p-3 rounded ${message.startsWith("Error") ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"}`}>
                  {message}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Jobs Table */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="p-6 border-b">
            <h2 className="text-lg font-semibold">Recent Jobs</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Workflow</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Attempt</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm font-mono text-gray-900">{job.id.slice(0, 12)}...</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{job.workflow_id}</td>
                    <td className="px-4 py-3">
                      <span className={`font-medium ${getStatusColor(job.status)}`}>{job.status}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">{job.attempt}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {job.error_code && <span className="text-red-600">{job.error_code}</span>}
                      {job.error_message && <span className="ml-2">{job.error_message.slice(0, 50)}...</span>}
                    </td>
                  </tr>
                ))}
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500">No jobs yet</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}