"use client";
import PlatformControlCatalog from "@/components/PlatformControlCatalog";
import { SysadminOnly } from "@/components/SysadminOnly";

export default function PlatformControlsPage() {
  return <SysadminOnly><PlatformControlCatalog /></SysadminOnly>;
}
