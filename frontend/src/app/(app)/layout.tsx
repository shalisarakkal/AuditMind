import AuthGuard from "@/components/AuthGuard";
import OrgGate from "@/components/OrgGate";
import Sidebar from "@/components/Sidebar";

/** Signed-in area: sidebar with org picker, pages scoped to the selected org. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-8">
          <OrgGate>{children}</OrgGate>
        </main>
      </div>
    </AuthGuard>
  );
}
