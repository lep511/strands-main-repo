from pydantic_monty import ClassInstance, AsyncMonty, Monty
import asyncio

# `ExternalModule` / `checkout(external_modules=...)` are documented but not yet
# released (pydantic-monty 1.1.0); expose a host object via `ClassInstance` instead.
class Tools:
    def add(self, a, b):
        return a + b


tools = ClassInstance(Tools(), allowed_methods=['add'])
code = 'tools.add(1, 2)'

with Monty() as pool:
    with pool.checkout() as session:
        result = session.feed_run(
            'double(x) + y',
            inputs={'x': 5, 'y': 6},
            external_lookup={'double': lambda x: x * 2},
        )
        print(result)

        session.feed_run(f'x = {result}')
        print(session.feed_run('x + 12'))

    with pool.checkout() as session:
        print(session.feed_run(code, inputs={'tools': tools}))


async def fetch(url: str) -> str:
    await asyncio.sleep(2.00)
    return f'contents of {url}'


async def main():
    async with AsyncMonty() as pool:
        async with pool.checkout() as session:
            result = await session.feed_run(
                "await fetch('https://example.com')",
                external_lookup={'fetch': fetch},
            )
    print(result)

asyncio.run(main())
