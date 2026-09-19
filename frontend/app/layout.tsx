import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'NightWatch — Infrastructure, alive.',description:'Your private infrastructure world and evidence-backed operations console.',robots:{index:false,follow:false}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>;}
