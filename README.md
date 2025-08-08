# Web Agent for creating backlinks

## Setup
- Use the format of sample env and add all the api keys.
```
cp .sample.env .env
```
- Add your `credentials.json`, it will ask for one time login when email verification is ever executed, after that your `token.pickle` file will stay consistent.
- Change the data accordingly in `business_data.json`. If needed then additional fields can also be added.
- Change the target URL in `main.py`
- Execute using
```
pip3 -r reqirements.txt
python3 main.py
```