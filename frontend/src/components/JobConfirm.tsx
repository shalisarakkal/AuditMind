"use client";

import { useState } from "react";

import ConfirmPanel from "@/components/ConfirmPanel";
import { useImports } from "@/context/ImportsContext";

/** What a row's Archive, Restore or Purge button asks to confirm. */
export type JobRequest = {
  /** The endpoint that starts the job. */
  path: string;
  label: string;
  message: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
};

/** Confirms a job, then starts and follows it (JobStatus shows how it goes;
 * lists reload when it finishes). */
export default function JobConfirm({ request, onClose }: { request: JobRequest; onClose(): void }) {
  const { startJob } = useImports();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await startJob(request.path);
      onClose();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <ConfirmPanel
        label={request.label}
        message={request.message}
        confirmLabel={request.confirmLabel}
        onConfirm={() => void confirm()}
        onCancel={onClose}
        busy={busy}
        danger={request.danger}
      />
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
    </div>
  );
}

/** Undo an archive that stopped part-way: bring back what it had archived. */
export function undoRequest(orgId: string, batchId: string, name: string): JobRequest {
  return {
    path: `/orgs/${orgId}/archive/${batchId}/restore`,
    label: `Undo archiving ${name}`,
    message: (
      <>
        Archiving <strong>{name}</strong> stopped part-way. Bring back what it had archived, and leave it as it was?
      </>
    ),
    confirmLabel: "Undo",
  };
}
