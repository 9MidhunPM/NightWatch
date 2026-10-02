'use client';

import { useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { ArrowUpRight, Check, ChevronDown, Menu, X } from 'lucide-react';
import { capabilities } from '@/lib/showcase-content';

export function PublicNavigation() {
  const [open, setOpen] = useState(false);
  return <header className="nw-header">
    <Link href="/" className="nw-brand"><span className="nw-mark" aria-hidden="true">N</span>NightWatch<span className="nw-brand-divider"/><span className="nw-brand-note">Infrastructure, alive.</span></Link>
    <button className="nw-menu" aria-label={open ? 'Close navigation' : 'Open navigation'} aria-expanded={open} aria-controls="public-navigation" onClick={() => setOpen(!open)}>{open ? <X size={21}/> : <Menu size={21}/>}</button>
    <nav id="public-navigation" aria-label="Main navigation" className={open ? 'is-open' : ''}>
      <a href="#how-it-works" onClick={() => setOpen(false)}>How it works</a>
      <a href="#inside" onClick={() => setOpen(false)}>The product</a>
      <a href="#build-story" onClick={() => setOpen(false)}>The story</a>
      <Link href="/login" className="nw-login-link">Operator sign-in <ArrowUpRight size={14}/></Link>
    </nav>
  </header>;
}

export function ProductExplorer() {
  const [selected, setSelected] = useState(0);
  const [loaded, setLoaded] = useState<Record<string, boolean>>({});
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const item = capabilities[selected];
  return <div className="nw-explorer">
    <div role="tablist" aria-label="NightWatch capabilities" className="nw-tabs" onKeyDown={event => {
      let next = selected;
      if (event.key === 'ArrowRight') next = (selected + 1) % capabilities.length;
      else if (event.key === 'ArrowLeft') next = (selected - 1 + capabilities.length) % capabilities.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = capabilities.length - 1;
      else return;
      event.preventDefault(); setSelected(next); tabs.current[next]?.focus();
    }}>
      {capabilities.map((capability, index) => <button ref={node => { tabs.current[index] = node; }} key={capability.id} id={`tab-${capability.id}`} role="tab" aria-selected={selected === index} aria-controls={`panel-${capability.id}`} tabIndex={selected === index ? 0 : -1} onClick={() => setSelected(index)}>{capability.label}<ChevronDown size={14}/></button>)}
    </div>
    {capabilities.map((capability, index) => <div key={capability.id} role="tabpanel" id={`panel-${capability.id}`} aria-labelledby={`tab-${capability.id}`} hidden={selected !== index} tabIndex={0}>
      <div className="nw-product-grid">
        <div className="nw-product-copy"><h3>{capability.title}</h3><p>{capability.description}</p><ul>{capability.features.map(feature => <li key={feature}><Check size={15} aria-hidden="true"/>{feature}</li>)}</ul><a href={capability.image} target="_blank" rel="noreferrer" className="nw-text-link">Open recorded screenshot <ArrowUpRight size={15}/></a></div>
        <figure className="nw-product-image"><div className="nw-window-bar"><span/><span/><span/><small>NightWatch / {capability.id}</small><span className="nw-recorded">Recorded product view</span></div><div className="nw-screenshot-frame"><Image src={capability.image} alt={capability.alt} width={capability.id === 'incidents' ? 1585 : 1600} height={capability.id === 'incidents' ? 1082 : 960} sizes="(max-width: 900px) 100vw, 65vw" loading="lazy" onLoad={() => setLoaded(current => ({...current, [capability.id]: true}))}/>{!loaded[capability.id] && <span className="nw-image-loading" aria-hidden="true">Loading recorded product view…</span>}</div><figcaption>{capability.label} · Recorded screenshot, not current telemetry</figcaption></figure>
      </div>
    </div>)}
    <span className="nw-sr-only" aria-live="polite">Showing {item.label}</span>
  </div>;
}
