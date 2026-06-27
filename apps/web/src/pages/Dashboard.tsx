import { PlaceholderScreen } from '@/components/placeholder-screen';
import { WordOfTheDay } from '@/components/word-of-the-day';

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <PlaceholderScreen
        title="Dashboard"
        description="Your languages and review progress will appear here."
      />
      {/* Experimental, flag-gated surface — renders nothing until the word_of_the_day flag is on. */}
      <WordOfTheDay />
    </div>
  );
}
