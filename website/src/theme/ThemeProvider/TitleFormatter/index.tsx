import React, { type ComponentProps, type ReactNode } from 'react';
import { TitleFormatterProvider } from '@docusaurus/theme-common/internal';
import type { Props } from '@theme/ThemeProvider/TitleFormatter';

type FormatterProp = ComponentProps<typeof TitleFormatterProvider>['formatter'];

const formatter: FormatterProp = ({ title, siteTitle, titleDelimiter }) => {
  const trimmedTitle = title?.trim();

  if (!trimmedTitle || trimmedTitle === siteTitle) {
    return siteTitle;
  }

  return `${siteTitle} ${titleDelimiter} ${trimmedTitle}`;
};

export default function ThemeProviderTitleFormatter({
  children,
}: Props): ReactNode {
  return (
    <TitleFormatterProvider formatter={formatter}>
      {children}
    </TitleFormatterProvider>
  );
}
