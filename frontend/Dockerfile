FROM node:20-alpine AS deps

WORKDIR /app

COPY package*.json ./

RUN npm ci

FROM deps AS dev

COPY . .

EXPOSE 80

CMD ["npm", "run", "server", "--", "--host", "0.0.0.0", "--port", "80"]

FROM deps AS build

COPY . .

RUN npm run build

FROM nginx:1.27-alpine AS prod

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
