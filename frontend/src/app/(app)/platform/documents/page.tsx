"use client";

import DocumentsLibrary from "@/components/DocumentsLibrary";
import { SysadminOnly } from "@/components/SysadminOnly";

export default function SharedDocumentsPage() {
  return <SysadminOnly><DocumentsLibrary platform writable /></SysadminOnly>;
}
