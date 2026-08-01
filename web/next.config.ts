import path from "node:path";

import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,

  outputFileTracingRoot: path.join(import.meta.dirname, "."),

  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default config;
