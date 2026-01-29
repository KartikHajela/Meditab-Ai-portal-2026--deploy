# 1. Use Python 3.12-slim to match your local version (3.12.8)
FROM python:3.12-slim

# 2. Set the working directory to the container's root
WORKDIR /code

# 3. Copy requirements FROM the initialization folder to the container root
#    This connects your "initialization/requirements.txt" to the container
COPY initialization/requirements.txt .

# 4. Install dependencies
#    We add --no-cache-dir to keep the image small and fast
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 5. Copy the ENTIRE project (backend, frontend, initialization, etc.)
COPY . .

# 6. The Command
#    We run uvicorn from the root folder ("/code")
#    We tell it to look inside the "backend" folder for "main.py"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]