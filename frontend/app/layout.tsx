import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={
 metadataBase:new URL('https://nightwatch.midhunpm.in'),
 title:'NightWatch — Infrastructure, alive.',
 description:'Meet NightWatch: a living 3D infrastructure world, evidence-backed investigations, and operations you stay in control of.',
 alternates:{canonical:'/'},
 robots:{index:true,follow:true},
 openGraph:{type:'website',url:'/',siteName:'NightWatch',title:'NightWatch — Infrastructure, alive.',description:'See your infrastructure. Follow the evidence. Keep it running.',images:[{url:'/showcase/nightwatch-social.jpg',width:1200,height:630,alt:'NightWatch infrastructure world and evidence-backed operations'}]},
 twitter:{card:'summary_large_image',title:'NightWatch — Infrastructure, alive.',description:'See your infrastructure. Follow the evidence. Keep it running.',images:['/showcase/nightwatch-social.jpg']}
};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>;}
