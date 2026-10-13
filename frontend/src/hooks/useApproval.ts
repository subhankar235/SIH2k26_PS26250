'use client';
import { useState } from 'react';
import { submitDecision } from '@/lib/api/approvals';

export function useApproval() {
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const approve = async (id: string, reviewer: string, reason: string) => {
    if (!reviewer.trim() || !reason.trim()) {
      throw new Error('Reviewer name and approval reason are strictly required.');
    }
    setSubmitting(true);
    try {
      await submitDecision(id, 'approved', reviewer, reason);
      setFeedback(`Approved item ${id} successfully.`);
      return true;
    } catch (e) {
      setFeedback(`Approval failed: ${(e as Error).message}`);
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const reject = async (id: string, reviewer: string, reason: string) => {
    if (!reviewer.trim() || !reason.trim()) {
      throw new Error('Reviewer name and rejection reason are strictly required.');
    }
    setSubmitting(true);
    try {
      await submitDecision(id, 'rejected', reviewer, reason);
      setFeedback(`Rejected item ${id}.`);
      return true;
    } catch (e) {
      setFeedback(`Rejection failed: ${(e as Error).message}`);
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  return { approve, reject, submitting, feedback, clearFeedback: () => setFeedback(null) };
}
