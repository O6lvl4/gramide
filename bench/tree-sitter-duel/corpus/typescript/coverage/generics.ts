export function first<const T extends readonly unknown[]>(values: T): T[number] | undefined { return values[0]; } export interface Store<T> { get<K extends keyof T>(key: K): T[K]; }
