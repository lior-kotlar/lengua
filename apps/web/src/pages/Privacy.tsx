/**
 * The published Privacy Policy page (`/privacy`, task 8.1.2) — the store-required, publicly reachable
 * GDPR notice. It is the web-rendered face of `docs/privacy-policy.md`; keep the two in sync when the
 * policy changes. Reachable without signing in (rendered in the {@link StaticLayout}).
 */
import { Link } from 'react-router-dom';

const CONTACT_EMAIL = 'privacy@lengua.app';

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-headline">{title}</h2>
      <div className="space-y-3 text-body text-muted-foreground">
        {children}
      </div>
    </section>
  );
}

export default function Privacy() {
  return (
    <article className="mx-auto max-w-3xl space-y-8">
      <header className="space-y-2">
        <h1 className="text-large-title">Privacy Policy</h1>
        <p className="text-subhead text-muted-foreground">
          Last updated: 2026-07-06
        </p>
      </header>

      <p className="text-body text-muted-foreground">
        This policy explains what personal data Lengua collects, why, the legal
        bases we rely on, who we share it with, and the rights you have under
        the EU General Data Protection Regulation (GDPR). Lengua is the data
        controller. For any question or request, contact us at{' '}
        <a
          className="text-primary hover:underline"
          href={`mailto:${CONTACT_EMAIL}`}
        >
          {CONTACT_EMAIL}
        </a>
        .
      </p>

      <Section title="What we collect, and why">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong className="text-foreground">
              Account &amp; authentication
            </strong>{' '}
            — your email address and the identifiers created when you sign up
            (including Google sign-in), to create and secure your account.
          </li>
          <li>
            <strong className="text-foreground">Learning content</strong> — the
            languages and CEFR levels you add, the vocabulary you enter, the
            sentences generated for you, your flashcards, your review history,
            and your derived proficiency, to provide the core service.
          </li>
          <li>
            <strong className="text-foreground">
              Content sent for AI generation
            </strong>{' '}
            — the vocabulary you submit and the sentences produced from it, sent
            to our AI language-model provider so it can write examples, add
            vowel marks, and explain words (see below).
          </li>
          <li>
            <strong className="text-foreground">
              Product analytics (opt-in only)
            </strong>{' '}
            — anonymized usage events, collected only after you explicitly opt
            in.
          </li>
          <li>
            <strong className="text-foreground">
              Error &amp; diagnostic data
            </strong>{' '}
            — technical error reports, to detect and fix problems and keep the
            service secure.
          </li>
        </ul>
        <p>
          We do not sell your personal data, use it for advertising, or build
          cross-site tracking profiles.
        </p>
      </Section>

      <Section title="Where your data is stored — Supabase (EU)">
        <p>
          Your account and all your learning data are stored in{' '}
          <strong className="text-foreground">Supabase</strong> (managed
          PostgreSQL + authentication) hosted in an{' '}
          <strong className="text-foreground">EU region</strong>. The Lengua
          backend runs on Google Cloud Run in an EU region, and the web frontend
          is served by Vercel.
        </p>
      </Section>

      <Section title="AI language-model provider">
        <p>
          Generating sentences, adding vowel marks, and explaining words is done
          by a third-party large-language-model (LLM) provider. In the
          production app you use, that provider is{' '}
          <strong className="text-foreground">Google Gemini</strong>. (Groq is
          used only in our internal development and testing environments, never
          with your real account data.) Because Gemini may process this content
          outside the EEA, such transfers are protected by appropriate
          safeguards — Standard Contractual Clauses and/or an adequacy decision.
        </p>
      </Section>

      <Section title="Legal bases (GDPR Article 6)">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong className="text-foreground">Contract</strong> — your
            account, your learning content, and sending your vocabulary to the
            LLM provider to deliver your results.
          </li>
          <li>
            <strong className="text-foreground">Consent</strong> — optional
            product analytics, which load only after you opt in and can be
            withdrawn at any time.
          </li>
          <li>
            <strong className="text-foreground">Legitimate interests</strong> —
            keeping the service secure, preventing abuse, and diagnosing errors.
          </li>
        </ul>
      </Section>

      <Section title="Sub-processors">
        <p>
          We share data only with the providers needed to run Lengua, each under
          a data-processing agreement:
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>Supabase — database &amp; authentication (EU region)</li>
          <li>
            Google (Gemini) — AI generation (production); may process outside
            the EEA under SCCs
          </li>
          <li>PostHog — product analytics (EU host), only if you opt in</li>
          <li>Sentry — error &amp; crash diagnostics</li>
          <li>Google Cloud (Cloud Run) — backend hosting (EU region)</li>
          <li>Vercel — web hosting</li>
        </ul>
      </Section>

      <Section title="Data retention">
        <p>
          We keep your account and learning data while your account is active.
          When you delete your account, your learning data and your
          authentication account are permanently erased, and the deletion
          cascades across all your data. Error/diagnostic data is kept only as
          long as needed to investigate issues.
        </p>
      </Section>

      <Section title="Your rights — export and delete your data">
        <p>
          Under the GDPR you can access, rectify, erase, restrict, and object to
          the processing of your data, request portability, and withdraw consent
          at any time. You may also complain to your local data-protection
          authority. Lengua gives you direct control over the two most important
          rights:
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong className="text-foreground">Export</strong> — in the app,
            open <em>Account → Export my data</em> to download your data as a
            JSON file.
          </li>
          <li>
            <strong className="text-foreground">Delete</strong> — delete your
            account in the app (<em>Account → Delete account</em>) or, without
            signing in, via the{' '}
            <Link to="/delete-account" className="text-primary hover:underline">
              account-deletion form
            </Link>
            . Both trigger the same permanent, cascading deletion, including
            removal of your Supabase authentication record.
          </li>
        </ul>
        <p>
          To exercise any other right, email{' '}
          <a
            className="text-primary hover:underline"
            href={`mailto:${CONTACT_EMAIL}`}
          >
            {CONTACT_EMAIL}
          </a>
          .
        </p>
      </Section>

      <Section title="Cookies and local storage">
        <p>
          Lengua does not use advertising or cross-site tracking cookies. The
          app stores a small amount of data locally to function: your theme and
          active-language preferences, your analytics-consent choice, and the
          session tokens that keep you signed in.
        </p>
      </Section>

      <Section title="Children">
        <p>
          Lengua is not directed to children under 16, and we do not knowingly
          collect their data. If you believe a child has provided us personal
          data, contact us and we will delete it.
        </p>
      </Section>

      <Section title="Contact">
        <p>
          Questions, requests, or complaints:{' '}
          <a
            className="text-primary hover:underline"
            href={`mailto:${CONTACT_EMAIL}`}
          >
            {CONTACT_EMAIL}
          </a>
          . See also our{' '}
          <Link to="/support" className="text-primary hover:underline">
            Support
          </Link>{' '}
          page.
        </p>
      </Section>
    </article>
  );
}
