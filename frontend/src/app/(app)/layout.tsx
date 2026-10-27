import AuthGuard from "@/components/AuthGuard";
import ApplicationHeader from "@/components/ApplicationHeader";
import OrgGate from "@/components/OrgGate";
import Sidebar from "@/components/Sidebar";
import FileDropGuard from "@/components/FileDropGuard";
import { ImportsProvider } from "@/context/ImportsContext";

/** Signed-in area: sidebar with org picker, pages scoped to the selected org.
 * Imports are followed here, above the pages, so they survive navigation. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <FileDropGuard />
      <ImportsProvider>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="min-w-0 flex-1 p-3 sm:p-8">
            <ApplicationHeader />
            <p className="mb-3 text-xs text-white/60">All times are displayed in your browser time zone.</p>
            <OrgGate>{children}</OrgGate>
          </main>
        </div>
      </ImportsProvider>
    </AuthGuard>
  );
}
