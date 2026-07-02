from app.graphql.schema import schema
import asyncio
import json

async def test_dino_predict():
    query = """
    mutation PredictDino($filename: String!) {
        predictDinoRqi(imageFilename: $filename)
    }
    """
    # Using a filename known to exist from previous steps
    variables = {"filename": "sv_4861_7175226e.jpg"}
    
    print(f"Testing DINO inference on {variables['filename']}...")
    result = await schema.execute(query, variable_values=variables)
    
    print(f"Errors: {result.errors}")
    print(f"Data: {json.dumps(result.data, indent=2)}")

if __name__ == "__main__":
    asyncio.run(test_dino_predict())
