import { describe, expect, it } from "vitest";

import { fileExtension, humanize, importTarget, readColumns, suggestProfile } from "@/lib/importProfiles";
import { BUILTIN_PROFILES, CUSTOM_EDR_PROFILE, ENDPOINT_PROFILE, GENERIC_FINDINGS_PROFILE, NETWORK_PROFILE } from "@/test/profiles";

describe("readColumns", () => {
  it("reads a CSV header row, with a BOM, quotes and CRLF", async () => {
    const file = new File(['﻿EndPointID,"Device, Name",LastHeartbeat\r\nEP-1,a,b\r\n'], "e.csv");
    expect(await readColumns(file)).toEqual(["EndPointID", "Device, Name", "LastHeartbeat"]);
  });

  it("reads the keys of the first JSON record, bare or wrapped", async () => {
    expect(await readColumns(new File(['[{"IPAddress": "1.1.1.1", "Hostname": "a"}]'], "s.json"))).toEqual([
      "IPAddress",
      "Hostname",
    ]);
    expect(await readColumns(new File(['{"records": [{"ResourceID": "x"}]}'], "c.JSON"))).toEqual(["ResourceID"]);
  });

  it("gives up quietly on anything it can't read", async () => {
    expect(await readColumns(new File(["{oops"], "bad.json"))).toEqual([]);
    expect(await readColumns(new File(["[1, 2]"], "nums.json"))).toEqual([]);
    expect(await readColumns(new File(["<x/>"], "scan.nessus"))).toEqual([]);
    expect(await readColumns(new File([""], "empty.csv"))).toEqual([]);
  });
});

describe("suggestProfile", () => {
  const endpointColumns = ["EndPointID", "DeviceName", "AgentVersion", "LastHeartbeat", "ThreatsDetected", "ComplianceStatus"];

  it("picks the profile whose columns are all in the file, ignoring case", () => {
    expect(suggestProfile(endpointColumns, BUILTIN_PROFILES)?.key).toBe("endpoint_agent");
    expect(suggestProfile(["ipaddress", "HOSTNAME", "OSDetected", "OpenPorts", "Extra"], BUILTIN_PROFILES)?.key).toBe(
      "network_scan",
    );
  });

  it("matches alternative column names and tolerates missing optional columns", () => {
    // The cloud file from the field: no name or environment column, "Type" not "ResourceType".
    const cloud = ["Provider", "ResourceID", "Type", "Region", "Owner", "Tags", "Status"];
    expect(suggestProfile(cloud, BUILTIN_PROFILES)?.key).toBe("cloud_inventory");
    const directory = ["AssetID", "Hostname", "Type", "OS", "Owner", "LastLogin", "Status"];
    expect(suggestProfile(directory, BUILTIN_PROFILES)?.key).toBe("directory");
  });

  it("needs at least half the profile's fields, and at least 3", () => {
    expect(suggestProfile(["DeviceName", "LastHeartbeat"], BUILTIN_PROFILES)).toBeNull();
    expect(suggestProfile(["ResourceID", "Type"], BUILTIN_PROFILES)).toBeNull();
    expect(suggestProfile([], BUILTIN_PROFILES)).toBeNull();
    // A profile mapping only 2 fields qualifies when both are found.
    const small = { ...GENERIC_FINDINGS_PROFILE, key: "small", builtin: false, column_map: { hostname: "Host", domain: "Area" } };
    expect(suggestProfile(["Host", "Area"], [small])?.key).toBe("small");
    expect(suggestProfile(["Host"], [small])).toBeNull();
  });

  it("prefers the profile that maps more columns, then the org's own", () => {
    const both = [...endpointColumns, "Device_Name"];
    expect(suggestProfile(both, [ENDPOINT_PROFILE, CUSTOM_EDR_PROFILE])?.key).toBe(CUSTOM_EDR_PROFILE.key);
    expect(suggestProfile(both, [CUSTOM_EDR_PROFILE, ENDPOINT_PROFILE])?.key).toBe(CUSTOM_EDR_PROFILE.key);
    const fewer = { ...NETWORK_PROFILE, column_map: { ip: "IPAddress" } };
    expect(suggestProfile(["IPAddress", "Hostname", "OSDetected", "OpenPorts"], [fewer, NETWORK_PROFILE])?.key).toBe(
      "network_scan",
    );
  });
});

describe("importTarget", () => {
  it("sends generic sources to the original endpoints and profiles to /imports", () => {
    expect(importTarget("o1", "generic_assets")).toEqual({ path: "/orgs/o1/assets/import", fields: {} });
    expect(importTarget("o1", "generic_findings")).toEqual({ path: "/orgs/o1/findings/import", fields: {} });
    expect(importTarget("o1", "endpoint_agent")).toEqual({ path: "/orgs/o1/imports", fields: { profile: "endpoint_agent" } });
  });
});

describe("helpers", () => {
  it("fileExtension and humanize", () => {
    expect(fileExtension("Scan.NESSUS")).toBe(".nessus");
    expect(fileExtension("noext")).toBe("");
    expect(humanize("open_ports")).toBe("Open ports");
    expect(humanize("endpoint_id")).toBe("Endpoint ID");
    expect(humanize("os")).toBe("OS");
    expect(humanize("region")).toBe("Region");
  });
});
