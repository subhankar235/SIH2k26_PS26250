"use client";
import { useRef, useState } from "react";
import { submitDecision } from "@/lib/api/approvals";
import type { Schedule } from "@/types/schedule";
export function useApproval() {
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const lock = useRef(false);
  async function submit(
    id: string,
    decision: "approved" | "rejected",
    reviewer: string,
    rationale: string,
    verification?: Schedule["verification"],
  ) {
    if (lock.current) return false;
    if (!reviewer.trim() || !rationale.trim()) {
      setFeedback("Reviewer and rationale are required.");
      return false;
    }
    if (decision === "approved" && verification !== "verified") {
      setFeedback("Only verified results can be approved.");
      return false;
    }
    lock.current = true;
    setSubmitting(true);
    setFeedback(null);
    setError(null);
    try {
      await submitDecision(id, decision, reviewer.trim(), rationale.trim());
      setFeedback(`Result ${decision}.`);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Review failed"));
      return false;
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  }
  return {
    approve: (
      id: string,
      reviewer: string,
      rationale: string,
      verification: Schedule["verification"],
    ) => submit(id, "approved", reviewer, rationale, verification),
    reject: (id: string, reviewer: string, rationale: string) =>
      submit(id, "rejected", reviewer, rationale),
    submitting,
    feedback,
    error,
    clearFeedback: () => setFeedback(null),
  };
}
