import Image from 'next/image';
import Link from 'next/link';
import { ArrowDown, ArrowRight, ArrowUpRight, Award, CircleCheck, Code2, GitBranch, Layers3, Play, Plus, ShieldCheck } from 'lucide-react';
import { PublicNavigation, ProductExplorer } from '@/components/showcase-interactions';
import { ShowcaseStage } from '@/components/showcase-stage';
import { capabilities, chapters, engineeringDetails, WALKTHROUGH } from '@/lib/showcase-content';
import '@fontsource-variable/manrope';
import './showcase.css';

export default function PublicShowcase() {
  return <div className="nw-public">
    <span hidden dangerouslySetInnerHTML={{__html: '<!-- THESIS: Infrastructure Theatre makes evidence-bound operations tangible. OWN-WORLD: Charcoal, mint, sculpted rock, silver servers, precise panels. STORY: Observe, investigate, understand, review, verify; then inspect the real product and build. FIRST VIEWPORT: Oversized left headline and actions, large right infrastructure diorama, quiet operator link. FORM: User-approved cinematic showcase with one native pinned narrative and readable product, architecture, and award sections. -->'}}/>
    <a href="#inside" className="nw-skip">Skip to the product</a>
    <PublicNavigation/>
    <main>
      <section id="theatre" className="nw-theatre" aria-label="NightWatch infrastructure story">
        <div className="nw-stage-backdrop"><ShowcaseStage/></div>
        <div className="nw-hero nw-container">
          <div className="nw-hero-copy">
            <a href="#build-story" className="nw-award"><Award size={14}/>Second Prize · Codex Community Hackathon<ArrowUpRight size={12}/></a>
            <h1>Infrastructure,<br/><span>alive.</span></h1>
            <p className="nw-hero-description">Your second set of eyes.<br/>An AI operations console that follows the evidence, prepares the change, and keeps you in control.</p>
            <div className="nw-hero-actions"><a href="#how-it-works" className="nw-button nw-button-primary">Explore NightWatch <ArrowDown size={17}/></a><a href={WALKTHROUGH} target="_blank" rel="noreferrer" className="nw-video-link"><span><Play size={13} fill="currentColor"/></span>Watch the walkthrough</a></div>
            <p className="nw-hero-footnote"><ShieldCheck size={13}/> Human approval. Observable outcomes.</p>
          </div>
          <div className="nw-hero-bottom"><a href="#how-it-works"><span className="nw-scroll-line"/>A little further. A much clearer picture.<ArrowDown size={14}/></a><span>Built by Midhun P M</span></div>
        </div>
        <div id="how-it-works" className="nw-story-intro nw-container"><span>Follow one incident</span><p>Representative incident simulation · illustrative evidence and outcomes</p><a href="#inside">Skip animation <ArrowDown size={13}/></a></div>
        <div className="nw-story nw-container">
          {chapters.map((chapter, index) => <article id={chapter.id} className={`nw-chapter nw-tone-${chapter.tone}`} key={chapter.id}>
            <div className="nw-chapter-copy"><div className="nw-chapter-label"><span>{String(index + 1).padStart(2, '0')}</span>{chapter.label}<span className="nw-chapter-rule"/></div><h2>{chapter.title.split('\n').map((line, i) => <span key={line}>{line}{i === 0 && <br/>}</span>)}</h2><p>{chapter.description}</p><dl className="nw-evidence">{chapter.lines.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><small className="nw-simulation"><span/>Illustrative evidence · {chapter.label.toLowerCase()} stage</small></div>
          </article>)}
        </div>
      </section>

      <section id="inside" className="nw-product-section">
        <div className="nw-container"><div className="nw-section-heading"><div><span className="nw-section-label"><Layers3 size={16}/> Inside NightWatch</span><h2>A world to explore.<br/>A console to get things done.</h2></div><p>The cinematic world is the beginning.<br/>{' '}The product behind it does the real work.</p></div><ProductExplorer/>
          <noscript><div className="nw-noscript-capabilities">{capabilities.map(capability => <article key={capability.id}><h3>{capability.title}</h3><p>{capability.description}</p><ul>{capability.features.map(feature => <li key={feature}>{feature}</li>)}</ul><a href={capability.image} className="nw-text-link">Open recorded {capability.label.toLowerCase()} screenshot</a></article>)}</div></noscript>
          <div className="nw-source-strip"><span>One reconciled infrastructure model</span><div>{['Dokploy', 'Docker', 'Beszel', 'Traefik', 'HTTP probes'].map(source => <span key={source}><CircleCheck size={13}/>{source}</span>)}</div></div>
        </div>
      </section>

      <section id="engineering" className="nw-engineering nw-container">
        <div className="nw-section-heading"><div><span className="nw-section-label"><Code2 size={16}/> Under the surface</span><h2>Intelligence has a place.<br/>So do boundaries.</h2></div><p>The model reasons about evidence.<br/>{' '}The application owns policy and execution.</p></div>
        <div className="nw-engineering-grid">
          <div className="nw-architecture"><div className="nw-architecture-header"><GitBranch size={18}/><span>The control plane</span><small>Separate service boundaries</small></div>
            <div className="nw-architecture-row"><span className="nw-architecture-icon">N</span><div><h3>Experience</h3><p>Next.js 16 · React 19 · TypeScript<br/>Three.js · React Three Fiber · Drei</p></div><span className="nw-architecture-tag">Frontend</span></div>
            <div className="nw-architecture-connection"><ArrowDown size={14}/><span>Signed session · allowlisted proxy</span></div>
            <div className="nw-architecture-row"><ShieldCheck size={25}/><div><h3>Observe. Reason. Review.</h3><p>FastAPI · Python 3.12 · Pydantic<br/>Typed tools · deterministic policy</p></div><span className="nw-architecture-tag">Backend</span></div>
            <div className="nw-architecture-connection"><ArrowDown size={14}/><span>Evidence · plans · operational history</span></div>
            <div className="nw-architecture-row"><Layers3 size={25}/><div><h3>Remember the evidence</h3><p>SQLite · SQLAlchemy Async · Alembic<br/>Observations, approvals, and verification</p></div><span className="nw-architecture-tag">Persistence</span></div>
            <div className="nw-architecture-footer"><span>Dokploy</span><span>Restricted Docker observer</span><span>Beszel</span><span>Routes & probes</span></div>
          </div>
          <div className="nw-engineering-details">{engineeringDetails.map(detail => <details key={detail.title}><summary>{detail.title}<Plus size={18}/></summary><p>{detail.text}</p></details>)}<div className="nw-engineering-note"><ShieldCheck size={16}/><p>Approval is tied to the exact plan. Verification is tied to observed evidence.</p></div></div>
        </div>
      </section>

      <section id="build-story" className="nw-build-story">
        <div className="nw-container nw-build-grid"><div className="nw-build-copy"><span className="nw-section-label"><Award size={17}/> Built in Calicut</span><h2>An idea.<br/>A hackathon.<br/><span>A second set of eyes.</span></h2><p>NightWatch took Second Prize at the Codex Community Hackathon Calicut, held at TinkerSpace on 19–20 September 2026.</p><p>Built by <strong>Midhun P M</strong>, with Codex as an engineering collaborator—from the first control-plane decisions to integration debugging, typed workflows, and the infrastructure world.</p><div className="nw-award-result"><Award size={27}/><div><strong>Second Prize</strong><span>Codex Community Hackathon Calicut · 2026</span></div></div><a href={WALKTHROUGH} target="_blank" rel="noreferrer" className="nw-text-link">Watch the narrated product walkthrough <ArrowUpRight size={16}/></a></div>
          <div className="nw-build-media"><figure className="nw-winners"><Image src="/showcase/top-three-winners.webp" alt="Event result graphic naming Midhun P M’s NightWatch as Second Prize at Codex Community Hackathon Calicut" width={1024} height={1536} sizes="(max-width: 900px) 100vw, 50vw"/><figcaption>The event result graphic. Calicut, September 2026.</figcaption></figure><div className="nw-event-images"><Image src="/showcase/codex-hackathon-calicut-builders.webp" alt="Builders working together at the Codex Community Hackathon at TinkerSpace" width={960} height={1280} sizes="(max-width: 900px) 55vw, 30vw"/><Image src="/showcase/midhun-builder-badge.webp" alt="Midhun P M’s Codex Community Hackathon builder badge" width={1204} height={1600} sizes="(max-width: 900px) 30vw, 15vw"/></div></div>
        </div>
      </section>

      <section className="nw-close nw-container"><span className="nw-mark nw-close-mark" aria-hidden="true">N</span><h2>See more.<br/><span>Keep it running.</span></h2><p>Get to know NightWatch in the narrated walkthrough.<br/>The operator console is a sign-in away.</p><div className="nw-close-actions"><a href={WALKTHROUGH} target="_blank" rel="noreferrer" className="nw-button nw-button-primary">Watch the walkthrough <Play size={15}/></a><Link href="/login" className="nw-button nw-button-outline">Operator sign-in <ArrowRight size={16}/></Link></div></section>
    </main>
    <footer className="nw-footer nw-container"><Link href="/" className="nw-brand"><span className="nw-mark" aria-hidden="true">N</span>NightWatch</Link><span>Built with intent. Operated with evidence.</span><a href="https://midhunpm.in" target="_blank" rel="noreferrer">Midhun P M <ArrowUpRight size={13}/></a></footer>
    <noscript><style>{'.nw-explorer,.nw-menu{display:none!important}.nw-header{display:block;position:static}.nw-header nav{display:flex!important;position:static!important;flex-direction:row!important;flex-wrap:wrap;gap:12px 20px;background:transparent;padding:14px 0 0;border:0}.nw-header nav .nw-login-link{width:auto;padding:0;border:0}'}</style></noscript>
  </div>;
}
