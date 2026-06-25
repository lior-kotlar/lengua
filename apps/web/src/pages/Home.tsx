import { Button } from '@/components/ui/button';

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-8 text-foreground">
      <h1 className="text-4xl font-bold tracking-tight">Lengua</h1>
      <p className="max-w-md text-center text-muted-foreground">
        Web shell scaffold. The React + Vite app for the Lengua
        language-learning platform.
      </p>
      <Button data-testid="cta-button">Get started</Button>
    </main>
  );
}
