import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
      <h1 className="text-3xl font-bold tracking-tight">Lengua</h1>
      <p className="text-muted-foreground">Web app placeholder — Phase 0 scaffold.</p>
      <Button>Get started</Button>
    </main>
  );
}
