/** @type {import('next').NextConfig} */
const previewDir = {
  ingest: ".next/statement-ingest",
  fuga: ".next/fuga-ingest",
  operational: ".next/report-operational",
  cloud: ".next/report-cloud",
}[process.env.ROYALTY_PREVIEW_SCENARIO];
const nextConfig = {
  devIndicators: false,
  ...(previewDir ? { distDir: previewDir } : {}),
};

export default nextConfig;
