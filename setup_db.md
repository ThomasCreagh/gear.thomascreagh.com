`sudo -u postgres psql`
```
CREATE USER gearuser WITH PASSWORD 'gearpass';
CREATE DATABASE gear OWNER gearuser;
GRANT ALL PRIVILEGES ON DATABASE gear TO gearuser;
\q
```
