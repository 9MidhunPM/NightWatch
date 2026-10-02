import type { NextConfig } from "next";
const config: NextConfig = {
 output: "standalone",
 poweredByHeader: false,
 async headers() {
  return [
   {source:"/:path*",headers:[{key:"X-Content-Type-Options",value:"nosniff"},{key:"Referrer-Policy",value:"same-origin"},{key:"X-Frame-Options",value:"DENY"}]},
   {source:"/:privatePath(login|world|overview|infrastructure|incidents|agent|deployments|reports|settings|api)/:path*",headers:[{key:"X-Robots-Tag",value:"noindex, nofollow"}]}
  ];
 }
};
export default config;
