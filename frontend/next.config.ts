import type { NextConfig } from "next";
import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

const nextConfig: NextConfig = {
  output: "export",
  transpilePackages: ["geist"],
  images: {
    unoptimized: true,
  },
};

export default withMDX(nextConfig);
