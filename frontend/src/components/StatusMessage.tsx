export default function StatusMessage({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) {
    return (
      <p role="alert" className="text-sm text-red-300">
        {error}
      </p>
    );
  }
  if (loading) return <p className="text-sm text-white/60">Loading…</p>;
  return null;
}
