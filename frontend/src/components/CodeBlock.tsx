export const CodeBlock: React.FC<{ code: string; language?: string }> = ({
  code,
  language = 'python',
}) => {
  return (
    <pre className={`language-${language} text-xs whitespace-pre overflow-x-auto`}>
      <code className={`language-${language}`}>{code}</code>
    </pre>
  );
};
