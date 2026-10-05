export type Getter<T> = { readonly [K in keyof T as `get${Capitalize<string & K>}`]?: () => T[K] }; export type Value<T> = T extends Promise<infer U> ? U : never;
