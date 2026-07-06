/**
 * The published Support page (`/support`, task 8.1.2) — the store-required, publicly reachable
 * support/contact URL. Reachable without signing in (rendered in the {@link StaticLayout}).
 */
import { Link } from 'react-router-dom';

const SUPPORT_EMAIL = 'privacy@lengua.app';

export default function Support() {
  return (
    <article className="mx-auto max-w-2xl space-y-8">
      <header className="space-y-2">
        <h1 className="text-large-title">Support</h1>
        <p className="text-subhead text-muted-foreground">
          Help with your Lengua account, your data, and privacy.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-headline">Contact us</h2>
        <p className="text-body text-muted-foreground">
          For help, questions, or data requests, email us at{' '}
          <a
            className="text-primary hover:underline"
            href={`mailto:${SUPPORT_EMAIL}`}
          >
            {SUPPORT_EMAIL}
          </a>
          . We aim to respond within 30 days for privacy and data-rights
          requests.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-headline">Your data</h2>
        <ul className="list-disc space-y-2 pl-5 text-body text-muted-foreground">
          <li>
            <strong className="text-foreground">Export</strong> — download
            everything in your account from <em>Account → Export my data</em> in
            the app.
          </li>
          <li>
            <strong className="text-foreground">Delete</strong> — delete your
            account in the app (<em>Account → Delete account</em>) or, without
            signing in, from the{' '}
            <Link to="/delete-account" className="text-primary hover:underline">
              account-deletion form
            </Link>
            .
          </li>
          <li>
            Read how we handle your data in our{' '}
            <Link to="/privacy" className="text-primary hover:underline">
              Privacy Policy
            </Link>
            .
          </li>
        </ul>
      </section>
    </article>
  );
}
