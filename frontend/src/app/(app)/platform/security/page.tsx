"use client";

import SecuritySettingsForm from "@/components/SecuritySettingsForm";
import { SysadminOnly } from "@/components/SysadminOnly";

/** The Sysadmin's security defaults: every org starts with them. */
export default function SecurityDefaultsPage() {
  return (
    <SysadminOnly>
      <div className="max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Security defaults</h1>
          <p className="mt-2 text-sm text-white/60">
            Every organization starts with these, and its admins may change them in Settings, within the same ranges.
            Settings marked Default are the built-in values. They also apply to the Sysadmin&apos;s own account.
          </p>
        </div>
        <SecuritySettingsForm path="/platform/security" editable belowName="built-in" />
      </div>
    </SysadminOnly>
  );
}
