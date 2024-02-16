# import tornado

# import minimalmodbus
# import time

# class MainHandler(tornado.web.RequestHandler):
# 	def get(self):
# 		return furnace.read_float(pv_read_register)

# def make_app():
# 	return tornado.web.Application([
# 		(r"/", MainHandler),
# 	])

# async def main():
# 	app = make_app()
# 	app.listen(8888)
# 	await asyncio.Event().wait()

# if __name__ == "__main__":
# 	#define furnace peripheral i/o object
# 	furnace = minimalmodbus.Instrument("COM6",1)
# 	furnace.serial.baudrate=9600

# 	#set register addresses
# 	pv_offset_register = 33050
# 	pv_read_register = 32770
# 	alt_sp_enable = 2*276+32000
# 	target_sp_register = 2*2 + 32000
# 	alt_sp_register = 2*26+32000	
# 	asyncio.run(main())

import asyncio

print()


import random
import time

async def part1(n: int) -> str:
    i = random.randint(0, 10)
    print(f"part1({n}) sleeping for {i} seconds.")
    await asyncio.sleep(i)
    result = f"result{n}-1"
    print(f"Returning part1({n}) == {result}.")
    return result

async def part2(n: int, arg: str) -> str:
    i = random.randint(0, 10)
    print(f"part2{n, arg} sleeping for {i} seconds.")
    await asyncio.sleep(i)
    result = f"result{n}-2 derived from {arg}"
    print(f"Returning part2{n, arg} == {result}.")
    return result

async def chain(n: int) -> None:
    start = time.perf_counter()
    p1 = await part1(n)
    p2 = await part2(n, p1)
    end = time.perf_counter() - start
    print(f"-->Chained result{n} => {p2} (took {end:0.2f} seconds).")

async def main(*args):
    await asyncio.gather(*(chain(n) for n in args))

if __name__ == "__main__":
    import sys
    random.seed(444)
    args = [1, 2, 3] if len(sys.argv) == 1 else map(int, sys.argv[1:])
    start = time.perf_counter()
    asyncio.run(main(*args))
    end = time.perf_counter() - start
    print(f"Program finished in {end:0.2f} seconds.")
