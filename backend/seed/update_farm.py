import asyncio
from sqlalchemy.future import select
from app.db.session import SessionLocal
from app.models.farm import Farm

async def update_farm_name():
    async with SessionLocal() as session:
        stmt = select(Farm).where(Farm.name == "Kebun Demo HuluHilir")
        result = await session.execute(stmt)
        farm = result.scalar_one_or_none()
        if farm:
            farm.name = "Kebun Demo PepperDex"
            await session.commit()
            print("Farm name updated to Kebun Demo PepperDex")
        else:
            print("Farm Kebun Demo HuluHilir not found.")

if __name__ == "__main__":
    asyncio.run(update_farm_name())
