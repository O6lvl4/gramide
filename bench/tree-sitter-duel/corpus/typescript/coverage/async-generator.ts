export async function* values(source: AsyncIterable<number>) { for await (const item of source) { yield await Promise.resolve(item); } }
