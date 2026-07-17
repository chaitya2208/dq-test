-- liquibase formatted sql
--changeset cshah:001 Create orders table
-- Intentionally missing a comment/owner + a couple of type issues to exercise DQ validation
CREATE TABLE PLAYGROUND_DB.SILVER.ORDERS (
    ORDER_ID     NUMBER(38,0),
    CUSTOMER_ID  NUMBER(38,0),
    STATUS       VARCHAR(20),
    ORDER_AMOUNT NUMBER(18,2),
    ORDER_DATE   TIMESTAMP_NTZ
);
