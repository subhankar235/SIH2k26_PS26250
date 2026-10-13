'use client';
import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardHeader, CardContent, Button, Spinner, Badge } from '@/components/ui';
import { getAgentRuns, submitAgentRequest } from '@/lib/api/agents';
import { AgentRun } from '@/types/agent';
import { Bot, Send, CheckCircle2, RefreshCw, GitBranch, ExternalLink, ArrowRight } from 'lucide-react';

export default function ExplanationsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getAgentRuns().then((data) => {
      setRuns(data);
      setLoading(false);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSubmitting(true);
    try {
      const newRun = await submitAgentRequest(query);
      setRuns((prev) => [newRun, ...prev]);
      setQuery('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent Explanations & Traces (F8)"
        description="Auditable reasoning chains, dependency lineage, and evidence-grounded agent actions"
        actions={
          <Badge variant="outline" className="border-sky-800 text-sky-300">
            <Bot size={12} className="mr-1 inline" /> Verifier-Grounded Agent
          </Badge>
        }
      />

      {/* Query Bar */}
      <Card className="border-slate-800 bg-slate-900/50">
        <CardContent className="pt-4">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask agent to explain a decision, investigate conflicting records, or audit lineage..."
              className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
            <Button
              type="submit"
              variant="primary"
              disabled={submitting || !query.trim()}
              className="flex items-center gap-1.5 bg-sky-600 hover:bg-sky-500 text-white"
            >
              {submitting ? <Spinner size="sm" /> : <Send size={14} />}
              <span>Ask Agent</span>
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Agent Runs List */}
      <div className="space-y-4">
        {loading ? (
          <div className="py-12 flex justify-center"><Spinner /></div>
        ) : (
          runs.map((run) => (
            <Card key={run.id} className="border-slate-800 bg-slate-900/40">
              <CardHeader
                title={run.query}
                subtitle={`Run ID: ${run.id} • Executed at ${run.createdAt} • ${run.retries} retries`}
                action={
                  <Badge variant="outline" className="border-emerald-800 text-emerald-300">
                    <CheckCircle2 size={12} className="mr-1 inline" /> {run.status.toUpperCase()}
                  </Badge>
                }
              />
              <CardContent className="space-y-4">
                {/* Node Trace Pipeline */}
                <div>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <GitBranch size={13} className="text-sky-400" /> Execution Node Pipeline
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {run.nodesVisited.map((node, i) => (
                      <React.Fragment key={node}>
                        <span className="px-2.5 py-1 rounded bg-slate-800/80 border border-slate-700/80 text-[11px] font-mono text-slate-300">
                          {node}
                        </span>
                        {i < run.nodesVisited.length - 1 && (
                          <ArrowRight size={12} className="text-slate-600" />
                        )}
                      </React.Fragment>
                    ))}
                  </div>
                </div>

                {/* Grounded Explanation */}
                <div className="p-3.5 rounded bg-slate-950/70 border border-slate-800 text-xs text-slate-200 leading-relaxed">
                  <div className="text-slate-400 font-semibold mb-1">Synthesized Reasoning:</div>
                  <p>{run.explanation}</p>
                </div>

                {/* Evidence Links */}
                <div>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Verified Evidence Links (Citations)
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {run.evidenceLinks.map((link) => (
                      <Link
                        key={link.id}
                        href={link.id.startsWith('REC') ? `/evidence/${link.id}` : `/validity`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-sky-950/40 border border-sky-800/60 text-xs text-sky-300 hover:bg-sky-900/50 transition-colors"
                      >
                        <ExternalLink size={12} />
                        <span>{link.label} (v{link.version})</span>
                      </Link>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
