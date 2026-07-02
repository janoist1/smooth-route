from app.graphql.schema import schema
import asyncio
import json

async def test_point():
    query = """
    query GetDinoTrainingData($id: Int!) {
        point(id: $id) {
            id
            imageUrl
            dinoRqiScore
            manualDinoRqi
        }
    }
    """
    variables = {"id": 4861}
    result = await schema.execute(query, variable_values=variables)
    
    print(f"Errors: {result.errors}")
    print(f"Data: {json.dumps(result.data, indent=2)}")

if __name__ == "__main__":
    asyncio.run(test_point())
