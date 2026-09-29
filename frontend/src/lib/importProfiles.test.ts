import { describe, expect, it } from "vitest";

import { fileExtension, firstJsonRecord, humanize, importTarget, readColumns, suggestProfile } from "@/lib/importProfiles";
import { BUILTIN_PROFILES, CUSTOM_EDR_PROFILE, ENDPOINT_PROFILE, GENERIC_FINDINGS_PROFILE, NETWORK_PROFILE } from "@/test/profiles";

describe("readColumns", () => {
  it("reads a large JSON file's columns from its start (e.g. a 50K-record cloud export)", async () => {
    const record = '{"Provider": "Azure", "ResourceID": "res-00001", "Type": "Lambda", "Region": "us-east-1", "Tags": {"env": "prod"}}';
    const big = new File(["[" + Array(60000).fill(record).join(",") + "]"], "cloud_assets50K.json");
    expect(big.size).toBeGreaterThan(5 * 1024 * 1024);

    expect(await readColumns(big)).toEqual(["Provider", "ResourceID", "Type", "Region", "Tags"]);
  });

  it("finds the first record whatever its values contain", () => {
    expect(firstJsonRecord('{"records": [{"Name": "a } { \\"b\\" [", "Tags": {"x": [1, {"y": 2}]}}, {"other": 1}]}')).toEqual({
      Name: 'a } { "b" [',
      Tags: { x: [1, { y: 2 }] },
    });
    expect(firstJsonRecord('[{"a": 1')).toBeNull(); // cut off: not complete yet
    expect(firstJsonRecord("[1, 2]")).toBeNull();
  });

  it("finds the records list, not a list that comes before it", () => {
    // An errors list first: the records are under "records".
    expect(firstJsonRecord('{"errors": [{"code": "E1"}], "records": [{"ResourceID": "r-1"}]}')).toEqual({ ResourceID: "r-1" });
    // Lists nested in another value, and brackets inside strings, don't count.
    expect(
      firstJsonRecord('{"meta": {"tags": [{"x": 1}], "note": "a [ { b"}, "value": [{"Hostname": "h"}]}'),
    ).toEqual({ Hostname: "h" });
    // No known key: the first list.
    expect(firstJsonRecord('{"count": 2, "value": [{"Hostname": "h"}]}')).toEqual({ Hostname: "h" });
    expect(firstJsonRecord('﻿  [ {"a": 1}]')).toEqual({ a: 1 });
  });

  it("reads the columns of a small file the same way", async () => {
    const file = new File(['{"errors": [{"code": "E1"}], "findings": [{"hostname": "h"}]}'], "f.json");
    expect(await readColumns(file)).toEqual(["hostname"]);
  });

  it("falls back to parsing a small file whose first record is cut off in the part read", async () => {
    const long = "x".repeat(300 * 1024);
    expect(await readColumns(new File([`[{"ResourceID": "r1", "Note": "${long}"}]`], "c.json"))).toEqual(["ResourceID", "Note"]);
  });

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
