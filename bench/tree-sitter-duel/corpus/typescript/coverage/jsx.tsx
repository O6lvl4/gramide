interface Props { title: string; } export const View = ({ title }: Props) => <section data-title={title}><h1>{title}</h1><input disabled /></section>;
