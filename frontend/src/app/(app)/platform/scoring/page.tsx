"use client";
import { SysadminOnly } from "@/components/SysadminOnly";
import StatusScoringSettings from "@/components/StatusScoringSettings";

export default function ScoringSettingsPage() {
  return <SysadminOnly><div className="min-w-0 space-y-6"><h1 className="text-2xl font-semibold">Scoring settings</h1><StatusScoringSettings editable /></div></SysadminOnly>;
}
