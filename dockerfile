# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the entire project and build dependencies
COPY . .

# Install Node.js
RUN apt-get update && apt-get install -y nodejs npm

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r app/backend/requirements.txt

# Install and build the frontend
RUN cd app/frontend && \
    npm install && \
    npm run build

# Environment variables can be set in a Dockerfile directly
ENV PORT 50505
ENV HOST 0.0.0.0

# Make port 50505 available to the world outside this container
EXPOSE 50505

# Run the application
CMD sh -c "cd app/backend && python -m quart --app main:app run --port $PORT --host $HOST --reload"

