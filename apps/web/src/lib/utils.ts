import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

/**
 * tailwind-merge taught our named type scale (tailwind.config.ts `fontSize`), so a caller's
 * `text-lg` correctly REPLACES a default like `text-title2` instead of both classes surviving and
 * the stylesheet order picking the winner. Without this, custom `text-*` names are misread as
 * text-colour classes and never conflict with font sizes.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        {
          text: [
            'large-title',
            'title1',
            'title2',
            'headline',
            'body',
            'subhead',
            'footnote',
            'caption',
          ],
        },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
