import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LanguageText } from '@/components/language-text';

const HEBREW_VOWELIZED = 'שָׁלוֹם';
const HEBREW_BARE = 'שלום';

describe('LanguageText', () => {
  it('renders LTR with no script font for a Latin-script language', () => {
    render(
      <LanguageText
        text="Hola mundo"
        language={{ code: 'es' }}
        showVowels={true}
      />,
    );
    const el = screen.getByText('Hola mundo');
    expect(el.tagName).toBe('P');
    expect(el).toHaveAttribute('dir', 'ltr');
    expect(el.className).not.toContain('font-arabic');
    expect(el.className).not.toContain('font-hebrew');
  });

  it('renders RTL in the Hebrew font for a Hebrew language', () => {
    render(
      <LanguageText
        text={HEBREW_VOWELIZED}
        language={{ code: 'he' }}
        showVowels={true}
      />,
    );
    const el = screen.getByText(HEBREW_VOWELIZED);
    expect(el).toHaveAttribute('dir', 'rtl');
    expect(el).toHaveAttribute('lang', 'he');
    expect(el.className).toContain('font-hebrew');
  });

  it('tags the element with the language code so screen readers use the right voice (WCAG 3.1.2)', () => {
    render(
      <LanguageText text="Hola mundo" language={{ code: 'es' }} showVowels />,
    );
    expect(screen.getByText('Hola mundo')).toHaveAttribute('lang', 'es');
  });

  it('omits lang when the language has no code', () => {
    render(<LanguageText text="?" language={{ code: null }} showVowels />);
    expect(screen.getByText('?')).not.toHaveAttribute('lang');
  });

  it('renders the Arabic font for an Arabic language', () => {
    render(
      <LanguageText text="مرحبا" language={{ code: 'ar' }} showVowels={true} />,
    );
    expect(screen.getByText('مرحبا').className).toContain('font-arabic');
  });

  it('strips diacritics when vowel marks are hidden', () => {
    render(
      <LanguageText
        text={HEBREW_VOWELIZED}
        language={{ code: 'he' }}
        showVowels={false}
      />,
    );
    expect(screen.getByText(HEBREW_BARE)).toBeInTheDocument();
    expect(screen.queryByText(HEBREW_VOWELIZED)).not.toBeInTheDocument();
  });

  it('renders as an inline span when asked, merging an extra className', () => {
    render(
      <LanguageText
        as="span"
        text="bonjour"
        language={{ code: 'fr' }}
        showVowels={true}
        className="font-medium"
      />,
    );
    const el = screen.getByText('bonjour');
    expect(el.tagName).toBe('SPAN');
    expect(el.className).toContain('font-medium');
  });
});
