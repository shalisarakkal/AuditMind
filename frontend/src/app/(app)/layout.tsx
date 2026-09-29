import AuthGuard from "@/components/AuthGuard";
import OrgGate from "@/components/OrgGate";
import Sidebar from "@/components/Sidebar";
import { ImportsProvider } from "@/context/ImportsContext";

/** Signed-in area: sidebar with org picker, pages scoped to the selected org.
 * Imports are followed here, above the pages, so they survive navigation. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <ImportsProvider>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 p-8">
            <OrgGate>{children}</OrgGate>
          </main>
        </div>
      </ImportsProvider>
    </AuthGuard>
  );
}
