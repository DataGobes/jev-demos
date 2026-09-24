{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
select * from {{ ref('stg_tickets') }}
where regexp_matches(body, '\b[A-Z]{2}\d{2}\s?[A-Z]{4}(\s?\d{4}){2}\s?\d{2}\b')              -- NL IBAN, spaced or not
   or regexp_matches(body, '(\+31|0031|\b0)[\s-]?6[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2}\b')  -- NL mobile
   or regexp_matches(body, '(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}')                          -- email
   or regexp_matches(body, '\b\d{4}\s?[A-Z]{2}\b')                                                -- NL postcode
   or regexp_matches(body, '(?i)\b[a-z]+(straat|laan|weg|plein|gracht|kade|singel)\s+\d+')        -- street + number
   or regexp_matches(body, '(?i)\b(born|date of birth|dob)\b')
