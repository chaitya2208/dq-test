-- liquibase formatted sql
--changeset cshah:002 Create customers table
CREATE TABLE PLAYGROUND_DB.SILVER.CUSTOMERS (
    CUSTOMER_ID  NUMBER(38,0) NOT NULL,
    EMAIL        VARCHAR(255) NOT NULL,
    FIRST_NAME   VARCHAR(100),
    LAST_NAME    VARCHAR(100),
    CREATED_AT   TIMESTAMP_NTZ NOT NULL
) COMMENT = 'Customer master table';
