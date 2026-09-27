export default function AssetsPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-white">Assets</h1>
      <p className="mt-2 text-sm text-white/60">
        Asset inventory table wires up to GET /orgs/:orgId/assets once auth + API client are connected.
      </p>
    </div>
  );
}
