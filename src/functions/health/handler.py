from mangum import Mangum

from src.shared.app import create_app
from src.shared import config
from src.shared.response import success_response


app = create_app("health-service")


@app.get("/health")
def health():
    return success_response(
        {
            "service": "popeyes-order-management-backend",
            "status": "ok",
            "stage": config.STAGE,
            "region": config.REGION,
        }
    )


lambda_handler = Mangum(app)
