import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        navy: "#0A1A2F",
        cyan: "#00C8FF",
      },
      backgroundImage: {
        "navy-cyan-gradient": "linear-gradient(135deg, #0A1A2F 0%, #00C8FF 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
