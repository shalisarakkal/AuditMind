import type { ImportProfile, ProfileField } from "@/lib/types";

// Test data shaped like GET /orgs/{id}/import-profiles.

const ASSET_FIELDS: ProfileField[] = ["type", "subtype", "hostname", "ip", "cloud_id", "environment", "criticality", "tags"].map(
  (name) => ({ name, label: name, detail: false }),
);

function profile(overrides: Partial<ImportProfile> & Pick<ImportProfile, "key" | "name" | "family">): ImportProfile {
  return {
    family_label: overrides.name,
    builtin: true,
    creates_assets: true,
    creates_findings: true,
    fields: ASSET_FIELDS,
    column_map: {},
    params: { default_values: {}, type_aliases: {}, keep_other_columns: false },
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

export const GENERIC_ASSETS_PROFILE = profile({
  key: "generic_assets",
  name: "Generic asset list",
  family: "generic_assets",
  creates_findings: false,
  column_map: Object.fromEntries(ASSET_FIELDS.map((f) => [f.name, f.name])),
});

export const GENERIC_FINDINGS_PROFILE = profile({
  key: "generic_findings",
  name: "Generic findings",
  family: "generic_findings",
  creates_assets: false,
  column_map: { hostname: "hostname", ip: "ip", domain: "domain", severity: "severity" },
});

export const ENDPOINT_PROFILE = profile({
  key: "endpoint_agent",
  name: "Endpoint agent export",
  family: "endpoint_agent",
  fields: [
    { name: "endpoint_id", label: "Endpoint ID", detail: true },
    { name: "hostname", label: "Hostname", detail: false },
    { name: "last_heartbeat", label: "Last heartbeat", detail: true },
    { name: "threats_detected", label: "Threats detected", detail: false },
    { name: "compliance_status", label: "Compliance status", detail: false },
  ],
  column_map: {
    endpoint_id: "EndPointID",
    hostname: "DeviceName",
    last_heartbeat: "LastHeartbeat",
    threats_detected: "ThreatsDetected",
    compliance_status: "ComplianceStatus",
  },
  params: {
    default_values: { type: "workstation", subtype: "endpoint" },
    type_aliases: {},
    keep_other_columns: true,
    threats_high_at: 1,
    threats_critical_at: 5,
    stale_after_days: 7,
    compliance_severity: { warning: "low", "non-compliant": "medium" },
    compliant_values: ["compliant"],
    day_first_dates: false,
  },
});

export const NETWORK_PROFILE = profile({
  key: "network_scan",
  name: "Network scan export",
  family: "network_scan",
  column_map: { ip: "IPAddress|IP", hostname: "Hostname", os: "OSDetected|OS", open_ports: "OpenPorts" },
  params: {
    default_values: {},
    type_aliases: {},
    keep_other_columns: true,
    no_vulnerability_values: ["none", "n/a"],
    risk_critical_at: 9,
    risk_high_at: 7,
    risk_medium_at: 4,
    vulnerability_domains: { "TLS1.0": "network_config" },
    risky_ports: { "23": { label: "Telnet", severity: "high" } },
  },
});

export const CLOUD_PROFILE = profile({
  key: "cloud_inventory",
  name: "Cloud inventory export",
  family: "cloud_inventory",
  creates_findings: false,
  column_map: {
    cloud_id: "ResourceID|ARN",
    hostname: "ResourceName|Name",
    type: "ResourceType|Type",
    region: "Region|Location",
    environment: "Environment|Env",
    tags: "Tags|Labels",
  },
  params: { default_values: {}, type_aliases: {}, keep_other_columns: true },
});

export const DIRECTORY_PROFILE = profile({
  key: "directory",
  name: "Directory (Active Directory) export",
  family: "directory",
  column_map: {
    asset_id: "AssetID|ObjectGUID",
    hostname: "Hostname|DNSHostName",
    type: "Type",
    os: "OS|OperatingSystem",
    owner: "Owner",
    last_login: "LastLogin|LastLogonDate",
    account_status: "Status|Enabled",
  },
  params: {
    default_values: {},
    type_aliases: {},
    keep_other_columns: true,
    disabled_values: ["disabled", "inactive"],
    disabled_severity: "low",
    ok_values: ["active", "pending"],
    stale_login_days: 90,
    stale_severity: "medium",
    day_first_dates: false,
  },
});

export const CUSTOM_EDR_PROFILE = profile({
  ...ENDPOINT_PROFILE,
  key: "c0ffee00-0000-0000-0000-000000000001",
  name: "Our EDR",
  family_label: "Endpoint agent export",
  builtin: false,
  column_map: { ...ENDPOINT_PROFILE.column_map, hostname: "Device_Name" },
  created_at: "2026-09-28T10:00:00Z",
  updated_at: "2026-09-28T10:00:00Z",
});

export const BUILTIN_PROFILES = [
  GENERIC_ASSETS_PROFILE,
  GENERIC_FINDINGS_PROFILE,
  ENDPOINT_PROFILE,
  NETWORK_PROFILE,
  CLOUD_PROFILE,
  DIRECTORY_PROFILE,
];

export const AZURE_PROFILE = profile({
  key: "azure_activity",
  name: "Azure Activity Log",
  family: "azure_activity",
  creates_assets: false,
  events: true,
  fields: ["time", "operation", "status", "caller", "subscription"].map((name) => ({ name, label: name, detail: false })),
  column_map: {
    time: "time|eventTimestamp",
    operation: "operation_name|operationName.value",
    status: "status.value|status",
    caller: "caller",
    subscription: "subscription_id|subscriptionId",
  },
  rules: [
    { key: "role_assignment_created", title: "Role assignment created", domain: "identity_access", severity: "high", min_events: 1 },
    { key: "failed_operations", title: "Failed operations", domain: "identity_access", severity: "medium", min_events: 10 },
  ],
});
